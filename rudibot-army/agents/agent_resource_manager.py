#!/usr/bin/env python3
"""Resource Manager Agent — Smart Load Distribution for RudiBot Army"""
import sys, os, time, json, subprocess, re, signal
from pathlib import Path
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram, load_state, save_state, get_env
from learner_mixin import AgentLearner

ID = "resource_manager"

@dataclass
class ResourceSnapshot:
    timestamp: str
    ram_used_percent: float
    ram_used_mb: int
    ram_total_mb: int
    cpu_percent: float
    disk_used_percent: float
    disk_free_gb: float
    load_avg_1m: float
    process_count: int

class ResourceManager:
    THRESHOLDS = {
        "ram_medium": 50, "ram_high": 70, "ram_critical": 85,
        "cpu_medium": 40, "cpu_high": 60, "cpu_critical": 80,
        "disk_warning": 85, "disk_critical": 95,
    }
    # Priority: lower number = can be offloaded first
    AGENT_PRIORITY = {
        "learner": 1, "social": 2, "finance": 3,
        "shopify": 4, "security": 5, "monitor": 99, "optimizer": 6,
    }
    MICRO_PRIORITY = {
        "micro_ai": 1, "micro_revenue": 2, "micro_ping": 3,
        "micro_backup": 4, "micro_clean": 5,
    }
    
    def __init__(self):
        self.learner = AgentLearner(ID)
        self._load_thresholds()
        self.history: list = []
        self.cloud_offloaded: set = set()
        self.last_action_time = 0
        self.cooldown_seconds = 300  # 5 min between actions
        
    def _load_thresholds(self):
        for key in self.THRESHOLDS:
            env_val = get_env(f"RM_{key.upper()}")
            if env_val:
                try:
                    self.THRESHOLDS[key] = float(env_val)
                except ValueError:
                    pass
    
    def _run_cmd(self, cmd: list, timeout=5) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
        except Exception:
            return ""
    
    def get_ram_info(self) -> tuple:
        """Returns (used_percent, used_mb, total_mb)"""
        # macOS vm_stat approach
        out = self._run_cmd(["vm_stat"])
        if not out:
            return (50.0, 24000, 48000)
        
        page_size = 16384  # macOS default
        values = {}
        for line in out.splitlines():
            if ":" in line:
                key = line.split(":")[0].strip().replace('"', '')
                val_str = line.split(":")[1].strip().rstrip('.')
                try:
                    values[key] = int(val_str)
                except ValueError:
                    pass
        
        active = values.get("Pages active", 0)
        inactive = values.get("Pages inactive", 0)
        wired = values.get("Pages wired down", 0)
        speculative = values.get("Pages speculative", 0)
        compressed = values.get("Pages occupied by compressor", 0)
        
        # macOS: inactive + speculative are reclaimable, don't count as real pressure
        real_used_pages = active + wired + compressed
        free_pages = values.get("Pages free", 0)
        speculative = values.get("Pages speculative", 0)
        total_pages = real_used_pages + free_pages + inactive + speculative
        
        if total_pages == 0:
            # Fallback: sysctl
            total_bytes_out = self._run_cmd(["sysctl", "-n", "hw.memsize"])
            try:
                total_mb = int(total_bytes_out.strip()) // (1024 * 1024)
            except Exception:
                total_mb = 48000
            used_mb = total_mb - (free_pages * page_size // (1024 * 1024))
            used_percent = (used_mb / total_mb) * 100 if total_mb > 0 else 50
            return (used_percent, used_mb, total_mb)
        
        used_mb = real_used_pages * page_size // (1024 * 1024)
        total_mb = total_pages * page_size // (1024 * 1024)
        used_percent = (real_used_pages / total_pages) * 100 if total_pages > 0 else 50
        return (used_percent, used_mb, total_mb)
    
    def get_cpu_percent(self) -> float:
        """Get CPU usage percentage"""
        out = self._run_cmd(["top", "-l", "1", "-n", "0", "-s", "0"])
        if out:
            match = re.search(r"CPU usage:\s+([\d.]+)%\s+user,\s+([\d.]+)%\s+sys", out)
            if match:
                return float(match.group(1)) + float(match.group(2))
        # Fallback: load average
        load_out = self._run_cmd(["sysctl", "-n", "vm.loadavg"])
        try:
            load = float(load_out.strip().replace('{', '').replace('}', '').split()[0])
            cores = os.cpu_count() or 8
            return (load / cores) * 100
        except Exception:
            return 30.0
    
    def get_disk_info(self) -> tuple:
        """Returns (used_percent, free_gb)"""
        out = self._run_cmd(["df", "-h", "/"])
        if out:
            lines = out.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    used_str = parts[4].replace('%', '')
                    try:
                        used = float(used_str)
                        # Get free space in GB
                        free_out = self._run_cmd(["df", "-g", "/"])
                        free_lines = free_out.strip().splitlines()
                        if len(free_lines) >= 2:
                            free_parts = free_lines[1].split()
                            if len(free_parts) >= 4:
                                free_gb = float(free_parts[3])
                                return (used, free_gb)
                    except ValueError:
                        pass
        return (50.0, 100.0)
    
    def get_load_avg(self) -> float:
        out = self._run_cmd(["sysctl", "-n", "vm.loadavg"])
        try:
            return float(out.strip().replace('{', '').replace('}', '').split()[0])
        except Exception:
            return 1.0
    
    def get_process_count(self) -> int:
        out = self._run_cmd(["ps", "ax"])
        return max(0, len(out.splitlines()) - 1)
    
    def collect_snapshot(self) -> ResourceSnapshot:
        ram_pct, ram_mb, total_mb = self.get_ram_info()
        disk_pct, free_gb = self.get_disk_info()
        return ResourceSnapshot(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            ram_used_percent=round(ram_pct, 1),
            ram_used_mb=ram_mb,
            ram_total_mb=total_mb,
            cpu_percent=round(self.get_cpu_percent(), 1),
            disk_used_percent=round(disk_pct, 1),
            disk_free_gb=round(free_gb, 1),
            load_avg_1m=round(self.get_load_avg(), 2),
            process_count=self.get_process_count(),
        )
    
    def determine_load_level(self, snap: ResourceSnapshot) -> str:
        ram = snap.ram_used_percent
        cpu = snap.cpu_percent
        disk = snap.disk_used_percent
        
        t = self.THRESHOLDS
        if ram >= t["ram_critical"] or cpu >= t["cpu_critical"] or disk >= t["disk_critical"]:
            return "critical"
        elif ram >= t["ram_high"] or cpu >= t["cpu_high"] or disk >= t["disk_warning"]:
            return "high"
        elif ram >= t["ram_medium"] or cpu >= t["cpu_medium"]:
            return "medium"
        return "low"
    
    def get_agent_processes(self) -> list:
        """Find running army agent processes"""
        out = self._run_cmd(["ps", "-axo", "pid,comm,args"])
        agents = []
        for line in out.splitlines()[1:]:
            parts = line.strip().split(None, 2)
            if len(parts) >= 3:
                pid, comm, args = parts[0], parts[1], parts[2]
                for agent_id in list(self.AGENT_PRIORITY.keys()) + list(self.MICRO_PRIORITY.keys()):
                    if agent_id.replace("_", "") in args.replace("_", "").replace("-", ""):
                        try:
                            rss_out = self._run_cmd(["ps", "-p", pid, "-o", "rss="])
                            rss_mb = int(rss_out.strip() or 0) // 1024
                            agents.append({"agent_id": agent_id, "pid": int(pid), "rss_mb": rss_mb})
                        except Exception:
                            pass
                        break
        return agents
    
    def offload_to_cloud(self, agent_id: str):
        """Mark agent for cloud execution"""
        self.cloud_offloaded.add(agent_id)
        state = load_state()
        if "cloud_offloaded" not in state:
            state["cloud_offloaded"] = []
        if agent_id not in state["cloud_offloaded"]:
            state["cloud_offloaded"].append(agent_id)
        save_state(state)
        notify_telegram(f"☁️ <b>Resource Manager:</b> {agent_id} → Cloud offloaded (RAM/CPU hoch)")
        print(f"  ☁️ Offloaded {agent_id} to cloud")
    
    def restore_from_cloud(self, agent_id: str):
        """Bring agent back locally"""
        if agent_id in self.cloud_offloaded:
            self.cloud_offloaded.discard(agent_id)
            state = load_state()
            if "cloud_offloaded" in state and agent_id in state["cloud_offloaded"]:
                state["cloud_offloaded"].remove(agent_id)
                save_state(state)
            notify_telegram(f"🏠 <b>Resource Manager:</b> {agent_id} → zurück lokal (Ressourcen OK)")
            print(f"  🏠 Restored {agent_id} to local")
    
    def throttle_agent(self, agent_id: str, pid: int):
        """Send SIGSTOP to temporarily pause an agent"""
        try:
            os.kill(pid, signal.SIGSTOP)
            print(f"  ⏸️ Throttled {agent_id} (PID {pid})")
            report(ID, "warning", f"throttled {agent_id}", {"pid": pid, "reason": "high_load"})
        except ProcessLookupError:
            pass
    
    def resume_agent(self, agent_id: str, pid: int):
        """Send SIGCONT to resume an agent"""
        try:
            os.kill(pid, signal.SIGCONT)
            print(f"  ▶️ Resumed {agent_id} (PID {pid})")
        except ProcessLookupError:
            pass
    
    def take_action(self, level: str, snap: ResourceSnapshot):
        now = time.time()
        if now - self.last_action_time < self.cooldown_seconds:
            return
        
        running = self.get_agent_processes()
        state = load_state()
        
        if level == "critical":
            # Stop non-critical agents
            candidates = [a for a in running 
                         if a["agent_id"] not in ["monitor", "security"]
                         and a["agent_id"] not in self.cloud_offloaded]
            candidates.sort(key=lambda x: self.AGENT_PRIORITY.get(x["agent_id"], 99))
            
            for agent in candidates[:3]:
                self.offload_to_cloud(agent["agent_id"])
                try:
                    os.kill(agent["pid"], signal.SIGTERM)
                    print(f"  🛑 Stopped {agent['agent_id']} (PID {agent['pid']})")
                except ProcessLookupError:
                    pass
            
            notify_telegram(
                f"🚨 <b>KRITISCHE LAST!</b>\n"
                f"RAM: {snap.ram_used_percent}% | CPU: {snap.cpu_percent}%\n"
                f"Agenten gestoppt: {', '.join(a['agent_id'] for a in candidates[:3])}"
            )
            self.last_action_time = now
            
        elif level == "high":
            # Offload low-priority agents
            candidates = [a for a in running 
                         if self.AGENT_PRIORITY.get(a["agent_id"], 99) <= 3
                         and a["agent_id"] not in self.cloud_offloaded]
            for agent in candidates[:2]:
                self.offload_to_cloud(agent["agent_id"])
            self.last_action_time = now
            
        elif level == "medium":
            # Throttle non-essential agents
            candidates = [a for a in running 
                         if self.AGENT_PRIORITY.get(a["agent_id"], 99) <= 2
                         and a["agent_id"] not in self.cloud_offloaded]
            for agent in candidates[:1]:
                self.throttle_agent(agent["agent_id"], agent["pid"])
            self.last_action_time = now
            
        elif level == "low":
            # Restore offloaded agents if stable
            if self.cloud_offloaded:
                for agent_id in list(self.cloud_offloaded)[:2]:
                    self.restore_from_cloud(agent_id)
            self.last_action_time = now
    
    def run(self):
        print(f"[{ID}] 🌡️ Resource Manager gestartet")
        print(f"  Schwellen: RAM {self.THRESHOLDS['ram_medium']}/{self.THRESHOLDS['ram_high']}/{self.THRESHOLDS['ram_critical']}%")
        print(f"  Schwellen: CPU {self.THRESHOLDS['cpu_medium']}/{self.THRESHOLDS['cpu_high']}/{self.THRESHOLDS['cpu_critical']}%")
        
        # Restore state
        state = load_state()
        self.cloud_offloaded = set(state.get("cloud_offloaded", []))
        
        cycle = 0
        while True:
            try:
                snap = self.collect_snapshot()
                level = self.determine_load_level(snap)
                
                self.history.append(asdict(snap))
                self.history = self.history[-100:]
                
                # Report to bus
                report(ID, level, f"RAM {snap.ram_used_percent}% | CPU {snap.cpu_percent}%", {
                    "snapshot": asdict(snap),
                    "load_level": level,
                    "cloud_offloaded": list(self.cloud_offloaded),
                    "history_count": len(self.history),
                })
                
                self.learner.log_cycle(level, f"RAM {snap.ram_used_percent}% CPU {snap.cpu_percent}%", {
                    "ram": snap.ram_used_percent,
                    "cpu": snap.cpu_percent,
                    "disk": snap.disk_used_percent,
                    "level": level,
                })
                
                # Console output
                icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(level, "⚪")
                print(f"  {icon} {snap.timestamp} | RAM {snap.ram_used_percent:5.1f}% | "
                      f"CPU {snap.cpu_percent:5.1f}% | Disk {snap.disk_used_percent:5.1f}% | "
                      f"Load {snap.load_avg_1m:.2f} | {level.upper()}")
                
                # Take action if needed
                self.take_action(level, snap)
                
                # Hourly summary
                cycle += 1
                if cycle % 12 == 0:
                    avg_ram = sum(h["ram_used_percent"] for h in self.history[-12:]) / 12
                    avg_cpu = sum(h["cpu_percent"] for h in self.history[-12:]) / 12
                    report(ID, "ok", f"1h avg: RAM {avg_ram:.1f}% CPU {avg_cpu:.1f}%", {
                        "avg_ram": round(avg_ram, 1),
                        "avg_cpu": round(avg_cpu, 1),
                        "offloaded": list(self.cloud_offloaded),
                    })
                
            except Exception as e:
                print(f"  ⚠️ Error: {e}")
                report(ID, "error", str(e)[:80])
            
            time.sleep(30)


if __name__ == "__main__":
    manager = ResourceManager()
    manager.run()
