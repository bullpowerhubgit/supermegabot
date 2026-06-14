"""Railway GraphQL API client — volumes, backups, deployments."""
import os
import logging
import aiohttp

log = logging.getLogger("RailwayClient")

RAILWAY_API = "https://backboard.railway.app/graphql/v2"


def _headers() -> dict:
    token = os.getenv("RAILWAY_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    async with aiohttp.ClientSession() as s:
        async with s.post(RAILWAY_API, json=payload, headers=_headers()) as r:
            data = await r.json()
            if "errors" in data:
                raise RuntimeError(data["errors"][0]["message"])
            return data.get("data", {})


# ── Projects ──────────────────────────────────────────────────────────────────

async def get_projects() -> list:
    q = """
    query {
      projects {
        edges { node { id name createdAt updatedAt } }
      }
    }
    """
    data = await _gql(q)
    return [e["node"] for e in data.get("projects", {}).get("edges", [])]


async def get_project(project_id: str) -> dict:
    q = """
    query project($id: String!) {
      project(id: $id) {
        id name createdAt
        services { edges { node { id name } } }
        environments { edges { node { id name } } }
      }
    }
    """
    data = await _gql(q, {"id": project_id})
    return data.get("project", {})


# ── Volumes ───────────────────────────────────────────────────────────────────

async def list_volumes(project_id: str) -> list:
    q = """
    query project($id: String!) {
      project(id: $id) {
        volumes {
          edges { node { id name createdAt } }
        }
      }
    }
    """
    data = await _gql(q, {"id": project_id})
    edges = data.get("project", {}).get("volumes", {}).get("edges", [])
    return [e["node"] for e in edges]


async def get_volume_instance(volume_instance_id: str) -> dict:
    q = """
    query volumeInstance($id: String!) {
      volumeInstance(id: $id) {
        id mountPath currentSizeMB state
        volume { id name }
        serviceInstance { serviceName }
      }
    }
    """
    data = await _gql(q, {"id": volume_instance_id})
    return data.get("volumeInstance", {})


async def create_volume(project_id: str, service_id: str, mount_path: str = "/data") -> dict:
    q = """
    mutation volumeCreate($input: VolumeCreateInput!) {
      volumeCreate(input: $input) { id name }
    }
    """
    data = await _gql(q, {"input": {
        "projectId": project_id,
        "serviceId": service_id,
        "mountPath": mount_path,
    }})
    return data.get("volumeCreate", {})


async def delete_volume(volume_id: str) -> bool:
    q = """
    mutation volumeDelete($volumeId: String!) {
      volumeDelete(volumeId: $volumeId)
    }
    """
    data = await _gql(q, {"volumeId": volume_id})
    return bool(data.get("volumeDelete"))


# ── Volume Backups ────────────────────────────────────────────────────────────

async def list_backups(volume_instance_id: str) -> list:
    q = """
    query volumeInstanceBackupList($volumeInstanceId: String!) {
      volumeInstanceBackupList(volumeInstanceId: $volumeInstanceId) {
        id name createdAt expiresAt usedMB referencedMB
      }
    }
    """
    data = await _gql(q, {"volumeInstanceId": volume_instance_id})
    return data.get("volumeInstanceBackupList", [])


async def create_backup(volume_instance_id: str) -> str:
    q = """
    mutation volumeInstanceBackupCreate($volumeInstanceId: String!) {
      volumeInstanceBackupCreate(volumeInstanceId: $volumeInstanceId)
    }
    """
    data = await _gql(q, {"volumeInstanceId": volume_instance_id})
    return data.get("volumeInstanceBackupCreate", "")


async def restore_backup(backup_id: str, volume_instance_id: str) -> bool:
    q = """
    mutation volumeInstanceBackupRestore($volumeInstanceBackupId: String!, $volumeInstanceId: String!) {
      volumeInstanceBackupRestore(
        volumeInstanceBackupId: $volumeInstanceBackupId,
        volumeInstanceId: $volumeInstanceId
      )
    }
    """
    data = await _gql(q, {
        "volumeInstanceBackupId": backup_id,
        "volumeInstanceId": volume_instance_id,
    })
    return bool(data.get("volumeInstanceBackupRestore"))


async def lock_backup(backup_id: str, volume_instance_id: str) -> bool:
    q = """
    mutation volumeInstanceBackupLock($volumeInstanceBackupId: String!, $volumeInstanceId: String!) {
      volumeInstanceBackupLock(
        volumeInstanceBackupId: $volumeInstanceBackupId,
        volumeInstanceId: $volumeInstanceId
      )
    }
    """
    data = await _gql(q, {
        "volumeInstanceBackupId": backup_id,
        "volumeInstanceId": volume_instance_id,
    })
    return bool(data.get("volumeInstanceBackupLock"))


async def delete_backup(backup_id: str, volume_instance_id: str) -> bool:
    q = """
    mutation volumeInstanceBackupDelete($volumeInstanceBackupId: String!, $volumeInstanceId: String!) {
      volumeInstanceBackupDelete(
        volumeInstanceBackupId: $volumeInstanceBackupId,
        volumeInstanceId: $volumeInstanceId
      )
    }
    """
    data = await _gql(q, {
        "volumeInstanceBackupId": backup_id,
        "volumeInstanceId": volume_instance_id,
    })
    return bool(data.get("volumeInstanceBackupDelete"))


# ── Backup Schedules ──────────────────────────────────────────────────────────

async def list_backup_schedules(volume_instance_id: str) -> list:
    q = """
    query volumeInstanceBackupScheduleList($volumeInstanceId: String!) {
      volumeInstanceBackupScheduleList(volumeInstanceId: $volumeInstanceId) {
        id name cron kind retentionSeconds createdAt
      }
    }
    """
    data = await _gql(q, {"volumeInstanceId": volume_instance_id})
    return data.get("volumeInstanceBackupScheduleList", [])


# ── Status check ──────────────────────────────────────────────────────────────

async def check_status() -> dict:
    token = os.getenv("RAILWAY_TOKEN", "")
    if not token:
        return {"status": "error", "message": "RAILWAY_TOKEN not set"}
    try:
        projects = await get_projects()
        return {
            "status": "ok",
            "projects": len(projects),
            "project_names": [p["name"] for p in projects],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
