from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import require_admin
from app.services.plugins.manager import plugin_manager, PluginStatus
from app.services.plugins.marketplace import marketplace
from app.services.plugins.manifest import discover_plugins

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginInstallRequest(BaseModel):
    package_name: str
    from_marketplace: bool = True


@router.get("")
async def list_plugins(status: str | None = None):
    plugins = plugin_manager.registry.get_all()
    result = {}
    for name, instance in plugins.items():
        if status and instance.status.value != status:
            continue
        result[name] = {
            "version": instance.manifest.version,
            "description": instance.manifest.description,
            "author": instance.manifest.author,
            "status": instance.status.value,
            "tools": instance.provided_tools,
            "providers": instance.provided_providers,
            "crash_count": instance.crash_count,
        }
    return {"plugins": result, "count": len(result)}


# Loading/installing a plugin runs third-party code in-process with the app's
# full privileges (there is no real isolation), so every mutating plugin action
# is admin-only.
@router.post("/discover")
async def discover_new_plugins(_admin: dict = Depends(require_admin)):
    manifests = discover_plugins()
    return {"discovered": len(manifests), "plugins": [m.name for m in manifests]}


@router.post("/load-all")
async def load_all_plugins(_admin: dict = Depends(require_admin)):
    results = plugin_manager.load_all()
    loaded = sum(1 for i in results.values() if i.status == PluginStatus.ACTIVE)
    failed = sum(1 for i in results.values() if i.status == PluginStatus.ERROR)
    return {"loaded": loaded, "failed": failed, "total": len(results)}


@router.post("/{plugin_name}/reload")
async def reload_plugin(plugin_name: str, _admin: dict = Depends(require_admin)):
    instance = plugin_manager.reload_plugin(plugin_name)
    if not instance:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"name": plugin_name, "status": instance.status.value}


@router.post("/{plugin_name}/disable")
async def disable_plugin(plugin_name: str, _admin: dict = Depends(require_admin)):
    success = plugin_manager.unload_plugin(plugin_name)
    if not success:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"name": plugin_name, "status": "disabled"}


@router.get("/tools")
async def list_plugin_tools():
    tools = plugin_manager.registry.get_tools()
    return {"tools": list(tools.keys()), "count": len(tools)}


# ─── Marketplace ───────────────────────────────────────

@router.get("/marketplace/search")
async def search_marketplace(query: str = "", limit: int = 20):
    results = await marketplace.search(query, limit)
    return {"query": query, "results": [{"name": p.name, "version": p.version, "description": p.description,
            "author": p.author, "rating": p.rating, "installs": p.installs, "verified": p.verified} for p in results]}


@router.get("/marketplace/{plugin_name}")
async def get_marketplace_plugin(plugin_name: str):
    plugin = await marketplace.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found in marketplace")
    return {"name": plugin.name, "version": plugin.version, "description": plugin.description,
            "author": plugin.author, "rating": plugin.rating, "installs": plugin.installs}


@router.post("/marketplace/install")
async def install_marketplace_plugin(
    payload: PluginInstallRequest, _admin: dict = Depends(require_admin)
):
    success = await marketplace.install(payload.package_name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Installation failed (invalid package name or pip error).",
        )

    manifests = discover_plugins()
    for m in manifests:
        if m.name == payload.package_name or payload.package_name in str(m.path):
            plugin_manager.load_plugin(m)
            break

    return {"package": payload.package_name, "installed": True}
