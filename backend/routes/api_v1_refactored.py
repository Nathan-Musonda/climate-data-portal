from .api_shared import api_v1
from .api_core_routes import register_core_routes
from .api_extra_routes import register_extra_routes
from .api_events_routes import register_event_routes
from .api_explorer_routes import register_explorer_routes
from .api_meta_routes import register_meta_routes


register_core_routes(api_v1)
register_extra_routes(api_v1)
register_event_routes(api_v1)
register_explorer_routes(api_v1)
register_meta_routes(api_v1)


__all__ = ['api_v1']
