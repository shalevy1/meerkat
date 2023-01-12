from typing import TYPE_CHECKING, Any, List, Tuple

from meerkat.interactive.endpoint import Endpoint, endpoint
from meerkat.errors import TriggerError

if TYPE_CHECKING:
    from meerkat.interactive.modification import Modification


@endpoint(prefix="/endpoint", route="/{endpoint}/dispatch/")
def dispatch(
    endpoint: Endpoint,
    fn_kwargs: dict,
    payload: dict = None,
) -> Tuple[Any, List["Modification"]]:
    # TODO: figure out how to use the payload
    """Call an endpoint."""
    from meerkat.interactive.modification import StoreModification

    try:
        result, modifications = endpoint.partial(**fn_kwargs).run()
    except TriggerError as e:
        # TODO: handle case where result is not none
        return {"result": None, "modifications": [], "error": str(e)}

    # only return store modifications that are not backend_only
    modifications = [
        m
        for m in modifications
        if not (isinstance(m, StoreModification) and m.backend_only)
    ]

    # Return the modifications and the result to the frontend
    return {"result": result, "modifications": modifications, "error": None}
