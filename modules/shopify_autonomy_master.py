"""
Shopify Autonomy Master — production-grade autonomous Shopify operator.

Jobs:
  order_orchestrator    — every 3 min, tags paid orders
  inventory_sync        — every 9 min, restocks below floor
  price_optimizer       — every 15 min (cron), adjusts prices ±delta%
  telegram_digest       — 4x/day, sends health digest
  recovery_reconciliation — every 2h, reconciles state
  catalog_watchdog      — every 4h, watches non-active products

Safety: all writes off by default (DRY_RUN=true). Enable via ENV:
  ENABLE_PRICE_WRITES=true
  ENABLE_INVENTORY_WRITES=true
  ENABLE_ORDER_TAGGING=true
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from apscheduler.events import (
    EVENT_JOB_ERROR, EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED, JobExecutionEvent,
)
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from filelock import FileLock, Timeout

UTC = timezone.utc
APP_NAME = "shopify_autonomy_master"
ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
LOCKS   = RUNTIME / "locks"
STATE   = RUNTIME / "state"
DLQ     = RUNTIME / "dead_letter"
DB      = RUNTIME / "db"
LOGS    = RUNTIME / "logs"
SQLITE_PATH = DB / "scheduler.sqlite"

for _d in (RUNTIME, LOCKS, STATE, DLQ, DB, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

log = logging.getLogger(APP_NAME)


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> set[str]:
    return {p.strip() for p in os.getenv(name, "").split(",") if p.strip()}


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: int = 5
    max_delay_seconds: int = 300
    exponential: bool = True

    def next_delay(self, attempt: int) -> int:
        factor = 1 if attempt <= 1 else (2 ** (attempt - 1) if self.exponential else attempt)
        return min(self.base_delay_seconds * factor, self.max_delay_seconds)


@dataclass(slots=True)
class SafetyConfig:
    dry_run: bool                    = _bool_env("DRY_RUN", True)
    enable_price_writes: bool        = _bool_env("ENABLE_PRICE_WRITES", False)
    enable_inventory_writes: bool    = _bool_env("ENABLE_INVENTORY_WRITES", False)
    enable_order_tagging: bool       = _bool_env("ENABLE_ORDER_TAGGING", True)
    allowed_product_ids: set[str]    = field(default_factory=lambda: _csv_env("ALLOWED_PRODUCT_IDS"))
    blocked_product_ids: set[str]    = field(default_factory=lambda: _csv_env("BLOCKED_PRODUCT_IDS"))
    allowed_variant_ids: set[str]    = field(default_factory=lambda: _csv_env("ALLOWED_VARIANT_IDS"))
    max_price_delta_percent: float   = float(os.getenv("MAX_PRICE_DELTA_PERCENT", "5.0"))
    max_variants_per_run: int        = int(os.getenv("MAX_VARIANTS_PER_RUN", "20"))
    max_products_per_run: int        = int(os.getenv("MAX_PRODUCTS_PER_RUN", "10"))
    max_inventory_items_per_run: int = int(os.getenv("MAX_INVENTORY_ITEMS_PER_RUN", "20"))
    min_allowed_price: float         = float(os.getenv("MIN_ALLOWED_PRICE", "1.0"))
    max_allowed_price: float         = float(os.getenv("MAX_ALLOWED_PRICE", "10000.0"))
    order_tag: str                   = os.getenv("AUTONOMY_ORDER_TAG", "autonomous-reviewed")

    def product_allowed(self, pid: str) -> bool:
        if pid in self.blocked_product_ids:
            return False
        return not self.allowed_product_ids or pid in self.allowed_product_ids

    def variant_allowed(self, vid: str) -> bool:
        return not self.allowed_variant_ids or vid in self.allowed_variant_ids


@dataclass(slots=True)
class JobDefinition:
    id: str
    func: Callable[..., Any]
    trigger: str
    cron: Optional[dict[str, Any]]     = None
    interval: Optional[dict[str, Any]] = None
    kwargs: dict[str, Any]             = field(default_factory=dict)
    tags: list[str]                    = field(default_factory=list)
    max_instances: int                 = 1
    coalesce: bool                     = True
    misfire_grace_time: int            = 300
    jitter: Optional[int]              = None
    retry_policy: RetryPolicy          = field(default_factory=RetryPolicy)
    lock_timeout: int                  = 1
    enabled: bool                      = True
    priority: str                      = "normal"
    description: str                   = ""


@dataclass(slots=True)
class RunRecord:
    run_id: str
    job_id: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: int
    attempt: int
    hostname: str
    pid: int
    error: Optional[str]              = None
    traceback: Optional[str]          = None
    metadata: dict[str, Any]          = field(default_factory=dict)


class JsonStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _file(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.base_dir / f"{digest}.json"

    def read(self, key: str, default: Optional[dict] = None) -> dict:
        path = self._file(key)
        if not path.exists():
            return default or {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return default or {}

    def write(self, key: str, value: dict) -> None:
        path = self._file(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True))
        tmp.replace(path)


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._v: dict[str, int] = {}

    def inc(self, key: str, n: int = 1):
        with self._lock:
            self._v[key] = self._v.get(key, 0) + n

    def set(self, key: str, n: int):
        with self._lock:
            self._v[key] = n

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._v)


class DeadLetterQueue:
    def push(self, record: RunRecord) -> Path:
        path = DLQ / f"{record.job_id}__{record.run_id}.json"
        path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True))
        return path


class NotificationSink:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id   = os.getenv("TELEGRAM_CHAT_ID", "")

    def notify(self, title: str, body: str, severity: str = "info"):
        log.warning("NOTIFY | %s | %s | %s", severity, title, body)
        if self.bot_token and self.chat_id:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": f"[{severity.upper()}] {title}\n{body}"},
                    timeout=10,
                )
            except Exception:
                log.exception("Telegram notification failed")


class JobLock:
    def __init__(self, job_id: str, timeout: int = 1):
        self.lock    = FileLock(str(LOCKS / f"{job_id}.lock"))
        self.timeout = timeout

    @contextmanager
    def acquire(self):
        try:
            self.lock.acquire(timeout=self.timeout)
            yield True
        except Timeout:
            yield False
        finally:
            try:
                self.lock.release()
            except Exception:
                pass


class ShopifyClient:
    def __init__(self):
        self.shop            = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        self.token           = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_TOKEN", "")
        self.api_version     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
        self.webhook_secret  = os.getenv("SHOPIFY_WEBHOOK_SECRET", os.getenv("SHOPIFY_SHARED_SECRET", ""))
        self.location_id     = os.getenv("SHOPIFY_LOCATION_ID", "")
        self.price_delta_pct = float(os.getenv("PRICE_DELTA_PERCENT", "2.5"))
        self.inventory_floor = int(os.getenv("INVENTORY_FLOOR", "3"))

    @property
    def enabled(self) -> bool:
        return bool(self.shop and self.token)

    @property
    def endpoint(self) -> str:
        return f"https://{self.shop}/admin/api/{self.api_version}/graphql.json"

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        if not self.enabled:
            raise RuntimeError("Shopify not configured")
        r = requests.post(
            self.endpoint,
            headers={"X-Shopify-Access-Token": self.token, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL errors: {payload['errors']}")
        return payload

    def verify_webhook(self, raw_body: bytes, hmac_header: str) -> bool:
        if not self.webhook_secret:
            raise RuntimeError("SHOPIFY_WEBHOOK_SECRET missing")
        digest = base64.b64encode(
            hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(digest, hmac_header)

    def recent_orders(self, first: int = 25, query_filter: str = "status:any") -> list[dict]:
        q = """query($first:Int!,$query:String!){orders(first:$first,query:$query,sortKey:UPDATED_AT,reverse:true){edges{node{id name displayFinancialStatus displayFulfillmentStatus createdAt updatedAt tags currentTotalPriceSet{shopMoney{amount currencyCode}}}}}}"""
        return [e["node"] for e in self.graphql(q, {"first": first, "query": query_filter})["data"]["orders"]["edges"]]

    def products(self, first: int = 30) -> list[dict]:
        q = """query($first:Int!){products(first:$first,sortKey:UPDATED_AT,reverse:true){edges{node{id title status totalInventory updatedAt}}}}"""
        return [e["node"] for e in self.graphql(q, {"first": first})["data"]["products"]["edges"]]

    def product_variants(self, first: int = 30, query_filter: str = "") -> list[dict]:
        q = """query($first:Int!,$query:String!){productVariants(first:$first,query:$query){edges{node{id title sku price inventoryQuantity inventoryItem{id sku}product{id title status}}}}}"""
        return [e["node"] for e in self.graphql(q, {"first": first, "query": query_filter})["data"]["productVariants"]["edges"]]

    def add_tags(self, resource_id: str, tags: list[str]) -> dict:
        m = """mutation($id:ID!,$tags:[String!]!){tagsAdd(id:$id,tags:$tags){node{id}userErrors{field message}}}"""
        payload = self.graphql(m, {"id": resource_id, "tags": tags})["data"]["tagsAdd"]
        if payload.get("userErrors"):
            raise RuntimeError(f"tagsAdd failed: {payload['userErrors']}")
        return payload

    def bulk_update_variant_prices(self, product_id: str, variants: list[dict]) -> dict:
        m = """mutation($productId:ID!,$variants:[ProductVariantsBulkInput!]!){productVariantsBulkUpdate(productId:$productId,variants:$variants){product{id}productVariants{id price}userErrors{field message}}}"""
        payload = self.graphql(m, {"productId": product_id, "variants": variants})["data"]["productVariantsBulkUpdate"]
        if payload.get("userErrors"):
            raise RuntimeError(f"bulk update failed: {payload['userErrors']}")
        return payload

    def set_inventory_quantities(self, reason: str, name: str, quantities: list[dict]) -> dict:
        m = """mutation($input:InventorySetQuantitiesInput!){inventorySetQuantities(input:$input){inventoryAdjustmentGroup{reason}userErrors{field message}}}"""
        payload = self.graphql(m, {"input": {"name": name, "reason": reason, "quantities": quantities}})["data"]["inventorySetQuantities"]
        if payload.get("userErrors"):
            raise RuntimeError(f"inventory set failed: {payload['userErrors']}")
        return payload


class MasterAutonomyService:
    def __init__(self):
        self.hostname    = socket.gethostname()
        self.instance_id = f"{self.hostname}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.state       = JsonStore(STATE)
        self.metrics     = Metrics()
        self.dlq         = DeadLetterQueue()
        self.notifier    = NotificationSink()
        self.shopify     = ShopifyClient()
        self.safety      = SafetyConfig()
        self._shutdown   = threading.Event()
        self.job_registry: dict[str, JobDefinition] = {}
        self.scheduler   = BackgroundScheduler(
            timezone=os.getenv("SCHEDULER_TIMEZONE", "Europe/Berlin"),
            jobstores={"default": MemoryJobStore()},
            executors={"default": ThreadPoolExecutor(int(os.getenv("SCHEDULER_THREADS", "8")))},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
        self.scheduler.add_listener(
            self._scheduler_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
        )

    def register(self, job: JobDefinition):
        if not job.enabled:
            return
        self.job_registry[job.id] = job
        trigger = CronTrigger(jitter=job.jitter, **(job.cron or {})) if job.trigger == "cron" else IntervalTrigger(jitter=job.jitter, **(job.interval or {}))
        self.scheduler.add_job(
            func=self._run_job_wrapper, trigger=trigger, id=job.id, replace_existing=True,
            kwargs={"job_id": job.id}, max_instances=job.max_instances,
            coalesce=job.coalesce, misfire_grace_time=job.misfire_grace_time,
        )
        log.info("Registered job=%s priority=%s", job.id, job.priority)

    def _scheduler_listener(self, event: JobExecutionEvent):
        codes = {EVENT_JOB_MISSED: "missed", EVENT_JOB_MAX_INSTANCES: "max_instances",
                 EVENT_JOB_EXECUTED: "executed", EVENT_JOB_ERROR: "error"}
        self.metrics.inc(f"jobs.{event.job_id}.{codes.get(event.code, 'unknown')}")

    def _run_job_wrapper(self, job_id: str):
        job = self.job_registry[job_id]
        with JobLock(job_id, timeout=job.lock_timeout).acquire() as acquired:
            if not acquired:
                self.metrics.inc(f"jobs.{job_id}.skipped_lock")
                return
            self._execute_with_retry(job)

    def _execute_with_retry(self, job: JobDefinition):
        attempt = 1
        while attempt <= job.retry_policy.max_attempts and not self._shutdown.is_set():
            t0 = time.perf_counter()
            started_at = datetime.now(UTC).isoformat()
            run_id = uuid.uuid4().hex
            try:
                result = job.func(self, **job.kwargs)
                dur = int((time.perf_counter() - t0) * 1000)
                self.metrics.inc(f"jobs.{job.id}.success")
                self._persist_run(RunRecord(run_id=run_id, job_id=job.id, status="success",
                    started_at=started_at, finished_at=datetime.now(UTC).isoformat(),
                    duration_ms=dur, attempt=attempt, hostname=self.hostname, pid=os.getpid(),
                    metadata={"result": self._safe_json(result), "priority": job.priority}))
                return
            except Exception as exc:
                dur = int((time.perf_counter() - t0) * 1000)
                tb = traceback.format_exc()
                rec = RunRecord(run_id=run_id, job_id=job.id, status="failed",
                    started_at=started_at, finished_at=datetime.now(UTC).isoformat(),
                    duration_ms=dur, attempt=attempt, hostname=self.hostname, pid=os.getpid(),
                    error=str(exc), traceback=tb, metadata={"tags": job.tags})
                self.metrics.inc(f"jobs.{job.id}.failed")
                self._persist_run(rec)
                log.exception("Job failed job=%s attempt=%d", job.id, attempt)
                if attempt >= job.retry_policy.max_attempts:
                    dlq_path = self.dlq.push(rec)
                    self.notifier.notify(f"Permanent failure: {job.id}", f"DLQ: {dlq_path.name}", severity="critical")
                    return
                delay = job.retry_policy.next_delay(attempt)
                self.notifier.notify(f"Retry {job.id}", f"Attempt {attempt} failed; retry in {delay}s", severity="warning")
                time.sleep(delay)
                attempt += 1

    def _persist_run(self, record: RunRecord):
        key = f"history:{record.job_id}"
        h = self.state.read(key, default={"runs": []})
        runs = h.get("runs", [])[-199:]
        runs.append(asdict(record))
        self.state.write(key, {"runs": runs, "updated_at": datetime.now(UTC).isoformat()})
        self.state.write(f"latest:{record.job_id}", asdict(record))

    def remember_change(self, namespace: str, entity_id: str, payload: dict):
        self.state.write(f"change:{namespace}:{entity_id}", payload)

    def last_change(self, namespace: str, entity_id: str) -> dict:
        return self.state.read(f"change:{namespace}:{entity_id}", default={})

    def mark_webhook_processed(self, webhook_id: str, topic: str):
        self.state.write(f"webhook:{webhook_id}", {"seen": True, "topic": topic, "marked_at": datetime.now(UTC).isoformat()})

    def webhook_seen(self, webhook_id: str) -> bool:
        return bool(self.state.read(f"webhook:{webhook_id}").get("seen"))

    def verify_incoming_webhook(self, raw_body: bytes, hmac_header: str, webhook_id: str, topic: str) -> dict:
        if self.webhook_seen(webhook_id):
            return {"ok": True, "duplicate": True}
        if not self.shopify.verify_webhook(raw_body, hmac_header):
            raise ValueError("Invalid Shopify HMAC")
        self.mark_webhook_processed(webhook_id, topic)
        return {"ok": True, "duplicate": False}

    def health(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "shopify_enabled": self.shopify.enabled,
            "shopify_domain": self.shopify.shop,
            "dry_run": self.safety.dry_run,
            "enable_price_writes": self.safety.enable_price_writes,
            "enable_inventory_writes": self.safety.enable_inventory_writes,
            "enable_order_tagging": self.safety.enable_order_tagging,
            "metrics": self.metrics.snapshot(),
            "jobs": [{"id": j.id, "next_run": getattr(j, "next_run_time", None) and
                      getattr(j, "next_run_time").isoformat()}
                     for j in self.scheduler.get_jobs()],
        }

    def start(self):
        self.scheduler.start()
        log.info("Autonomy master started instance=%s dry_run=%s", self.instance_id, self.safety.dry_run)
        self.notifier.notify("Shopify Autonomy Master gestartet",
                             f"dry_run={self.safety.dry_run} | {len(self.job_registry)} jobs aktiv", severity="info")

    def stop(self):
        self._shutdown.set()
        self.scheduler.shutdown(wait=False)

    @staticmethod
    def _safe_json(v: Any) -> Any:
        try:
            json.dumps(v)
            return v
        except Exception:
            return str(v)


# ── Job implementations ───────────────────────────────────────────────────────

def order_orchestrator(svc: MasterAutonomyService) -> dict:
    if not svc.shopify.enabled:
        return {"mode": "dry-run", "message": "Shopify not configured"}
    orders = svc.shopify.recent_orders(first=25)
    actionable = [o for o in orders if o.get("displayFinancialStatus") in {"PAID", "AUTHORIZED", "PARTIALLY_PAID"}]
    tagged, skipped, dry = 0, 0, []
    for o in actionable[:10]:
        if svc.safety.order_tag in (o.get("tags") or []):
            skipped += 1
            continue
        if svc.safety.dry_run or not svc.safety.enable_order_tagging:
            dry.append(o["id"])
        else:
            svc.shopify.add_tags(o["id"], [svc.safety.order_tag])
            tagged += 1
    svc.metrics.set("orders.actionable", len(actionable))
    svc.metrics.set("orders.tagged", tagged)
    return {"fetched": len(orders), "actionable": len(actionable), "tagged": tagged, "skipped": skipped, "dry": dry[:5]}


def inventory_sync(svc: MasterAutonomyService) -> dict:
    if not svc.shopify.enabled:
        return {"mode": "dry-run"}
    if not svc.shopify.location_id:
        return {"mode": "guarded", "message": "SHOPIFY_LOCATION_ID missing"}
    variants = svc.shopify.product_variants(first=max(svc.safety.max_inventory_items_per_run, 30))
    quantities, low, dry = [], 0, []
    for v in variants:
        pid, vid = (v.get("product") or {}).get("id"), v.get("id")
        if not pid or not svc.safety.product_allowed(pid) or not svc.safety.variant_allowed(vid):
            continue
        qty = int(v.get("inventoryQuantity") or 0)
        if qty < svc.shopify.inventory_floor:
            low += 1
            item_id = (v.get("inventoryItem") or {}).get("id")
            if item_id:
                entry = {"inventoryItemId": item_id, "locationId": svc.shopify.location_id,
                         "quantity": svc.shopify.inventory_floor, "compareQuantity": qty}
                (dry if (svc.safety.dry_run or not svc.safety.enable_inventory_writes) else quantities).append(entry)
        if len(quantities) >= svc.safety.max_inventory_items_per_run:
            break
    if quantities:
        svc.shopify.set_inventory_quantities("correction", "available", quantities)
        for q in quantities:
            svc.remember_change("inventory", q["inventoryItemId"],
                                {"quantity": q["quantity"], "changed_at": datetime.now(UTC).isoformat()})
    svc.metrics.set("inventory.low_stock", low)
    svc.metrics.set("inventory.corrected", len(quantities))
    return {"checked": len(variants), "low_stock": low, "corrected": len(quantities), "dry": dry[:5]}


def price_optimizer(svc: MasterAutonomyService) -> dict:
    if not svc.shopify.enabled:
        return {"mode": "dry-run"}
    delta = min(svc.shopify.price_delta_pct, svc.safety.max_price_delta_percent)
    variants = svc.shopify.product_variants(first=max(svc.safety.max_variants_per_run, 30))
    grouped: dict[str, list] = {}
    touched, touched_prods, dry = 0, set(), []
    for v in variants:
        pid, vid = (v.get("product") or {}).get("id"), v.get("id")
        if not pid or not svc.safety.product_allowed(pid) or not svc.safety.variant_allowed(vid):
            continue
        if len(touched_prods) >= svc.safety.max_products_per_run and pid not in touched_prods:
            continue
        price = float(v.get("price") or 0)
        if price <= 0:
            continue
        new_price = round(price * (1 + delta / 100), 2)
        if not (svc.safety.min_allowed_price <= new_price <= svc.safety.max_allowed_price):
            continue
        if svc.last_change("price", vid).get("new_price") == new_price:
            continue
        payload = {"id": vid, "price": f"{new_price:.2f}"}
        touched_prods.add(pid)
        touched += 1
        (dry if (svc.safety.dry_run or not svc.safety.enable_price_writes) else grouped.setdefault(pid, [])).append(payload) if (svc.safety.dry_run or not svc.safety.enable_price_writes) else grouped.setdefault(pid, []).append(payload)
        if touched >= svc.safety.max_variants_per_run:
            break
    updated_p, updated_v = 0, 0
    for pid, items in grouped.items():
        svc.shopify.bulk_update_variant_prices(pid, items[:50])
        updated_p += 1
        updated_v += len(items[:50])
        for item in items[:50]:
            svc.remember_change("price", item["id"], {"new_price": item["price"], "changed_at": datetime.now(UTC).isoformat()})
    svc.metrics.set("pricing.updated_products", updated_p)
    svc.metrics.set("pricing.updated_variants", updated_v)
    return {"updated_products": updated_p, "updated_variants": updated_v, "delta_percent": delta, "dry": dry[:5]}


def telegram_digest(svc: MasterAutonomyService) -> dict:
    h = svc.health()
    svc.notifier.notify("Shopify Autonomy Digest",
                        f"Jobs: {len(h['jobs'])} | Metrics: {len(h['metrics'])} | Shopify: {h['shopify_enabled']} | DryRun: {h['dry_run']}")
    return {"sent": True, "job_count": len(h["jobs"])}


def recovery_reconciliation(svc: MasterAutonomyService) -> dict:
    return {
        "reconciled": True,
        "order_state":     bool(svc.state.read("latest:order_orchestrator")),
        "inventory_state": bool(svc.state.read("latest:inventory_sync")),
        "pricing_state":   bool(svc.state.read("latest:price_optimizer")),
    }


def catalog_watchdog(svc: MasterAutonomyService) -> dict:
    if not svc.shopify.enabled:
        return {"mode": "dry-run"}
    products = svc.shopify.products(first=50)
    non_active = [p for p in products if p.get("status") != "ACTIVE"]
    svc.metrics.set("catalog.non_active", len(non_active))
    return {"scanned": len(products), "non_active": len(non_active), "sample": [p["title"] for p in non_active[:5]]}


# ── Service factory ───────────────────────────────────────────────────────────

_service_instance: MasterAutonomyService | None = None


def get_service() -> MasterAutonomyService:
    global _service_instance
    if _service_instance is None:
        _service_instance = build_master_service()
        _service_instance.start()
    return _service_instance


def build_master_service() -> MasterAutonomyService:
    svc = MasterAutonomyService()
    svc.register(JobDefinition(
        id="order_orchestrator", func=order_orchestrator, trigger="interval",
        interval={"minutes": 3}, priority="critical", tags=["orders"],
        jitter=10, retry_policy=RetryPolicy(6, 3, 90), description="Realtime order orchestration"))
    svc.register(JobDefinition(
        id="inventory_sync", func=inventory_sync, trigger="interval",
        interval={"minutes": 9}, priority="high", tags=["inventory"],
        jitter=20, description="Inventory sync and stock watch"))
    svc.register(JobDefinition(
        id="price_optimizer", func=price_optimizer, trigger="cron",
        cron={"minute": "7,22,37,52"}, priority="high", tags=["pricing"],
        jitter=15, retry_policy=RetryPolicy(4, 8, 120), description="Autonomous repricing"))
    svc.register(JobDefinition(
        id="telegram_digest", func=telegram_digest, trigger="cron",
        cron={"minute": "0", "hour": "8,12,18,23"}, priority="normal", tags=["alerts"],
        description="Digest to Telegram"))
    svc.register(JobDefinition(
        id="recovery_reconciliation", func=recovery_reconciliation, trigger="cron",
        cron={"minute": "13", "hour": "*/2"}, priority="critical", tags=["recovery"],
        jitter=30, retry_policy=RetryPolicy(7, 5, 180), description="State reconciliation"))
    svc.register(JobDefinition(
        id="catalog_watchdog", func=catalog_watchdog, trigger="cron",
        cron={"minute": "17", "hour": "*/4"}, priority="normal", tags=["catalog"],
        jitter=25, description="Catalog drift watcher"))
    return svc


def main():
    svc = build_master_service()
    svc.start()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: svc.stop())
    log.info("Health: %s", json.dumps(svc.health(), indent=2))
    while not svc._shutdown.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()


async def run_with_brutus_traffic() -> dict:
    """Run Shopify autonomy check then fire BRUTUS traffic for the shop."""
    result = {}
    try:
        svc = get_service()
        result["catalog"] = catalog_watchdog(svc)
    except Exception as e:
        result["shopify_error"] = str(e)
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        shop = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        result["brutus"] = await run_brutus_swarm(
            keywords=["Shopify Shop automatisieren 2026", "Shopify SEO Produkte", "Online Shop passives Einkommen"],
            max_keywords=3,
        )
    except Exception as e:
        result["brutus_error"] = str(e)
    return result
