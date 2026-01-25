from __future__ import annotations


def resolve_create_invite_callable():
    try:
        from app.domains.simulations import service as sim_service

        if getattr(sim_service, "create_invite", None):
            return sim_service.create_invite
    except Exception:
        pass
    from .invite_create import create_invite

    return create_invite
