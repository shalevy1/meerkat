import code
import os
from functools import partial, wraps
from typing import Callable

from fastapi import HTTPException
from IPython.display import IFrame
from pydantic import BaseModel

from meerkat.constants import APP_DIR
from meerkat.interactive.app.src.lib.component.abstract import (
    Component,
    ComponentFrontend,
)
from meerkat.mixins.identifiable import IdentifiableMixin
from meerkat.state import state


def interface(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        interface = Interface(component=partial(fn, *args, **kwargs))
        return interface.launch()

    return wrapper


class InterfaceFrontend(BaseModel):
    component: ComponentFrontend
    name: str


class Interface(IdentifiableMixin):

    _self_identifiable_group: str = "interfaces"

    def __init__(
        self,
        component: Component,
        name: str = "Interface",
        id: str = None,
        height: str = "1000px",
        width: str = "100%",
    ):

        super().__init__(id=id)

        self.component = component
        self.name = name
        self.height = height
        self.width = width
        
        self.write_component_wrappers()
        self.write_sveltekit_route()

    def _to_svelte(self):

        # Check if we're in a Meerkat generated app
        # These apps are generated with the `mk init` command
        # They have a .mk file in the `app` directory
        import_prefix = "$lib"
        if os.path.exists(os.path.join(APP_DIR, ".mk")):
            # In a Meerkat generated app
            # Use the @meerkat-ml/meerkat package instead of $lib
            import_prefix = "@meerkat-ml/meerkat"

        all_components = list(sorted(self.component.get_components()))
        import_block = "\n".join(
            [
                f"    import {component} from '$lib/wrappers/{self.id}/{component}.svelte';"
                for component in all_components
            ]
        )

        component_mapping = [f"        {c}: {c}," for c in all_components]
        component_mapping = "\n".join(component_mapping)

        svelte = f"""\
<script lang="ts">
    import banner from '$lib/assets/banner_small.png';
    import {{ API_URL }} from '{import_prefix}';
    import { "Interface" if import_prefix == "$lib" else "{ Interface }" } from '{import_prefix}';
    import {{ onMount, setContext }} from 'svelte';

{import_block}

    setContext("Components", {{
{component_mapping}
    }})

    let config: Interface | null = null;
    onMount(async () => {{
        config = await (await fetch(`${{$API_URL}}/interface/{self.id}/config`)).json();
        document.title = "{self.name}";
    }});
</script>

<div class="h-screen p-3">
    {{#if config}}
        <Interface {{config}} />
    {{:else}}
        <div class="flex justify-center h-screen items-center">
            <img src={{banner}} alt="Meerkat" class="h-12" />
        </div>
    {{/if}}
</div>
"""
        return svelte

    def write_component_wrappers(self):
        wrappers = self.component.to_svelte_wrapper()
        os.makedirs(f"{APP_DIR}/src/lib/wrappers/{self.id}/", exist_ok=True)
        for component_name, wrapper in wrappers.items():
            with open(
                f"{APP_DIR}/src/lib/wrappers/{self.id}/{component_name}.svelte",
                "w",
            ) as f:
                f.write(wrapper)

    def write_sveltekit_route(self):
        """Each Interface writes to a new SvelteKit route."""
        os.makedirs(f"{APP_DIR}/src/routes/{self.id}", exist_ok=True)
        if os.path.exists(f"{APP_DIR}/src/routes/{self.id}/+page.svelte"):
            raise ValueError(
                f"Interface with id {self.id} already exists. "
                "Please use a different id."
            )
        with open(f"{APP_DIR}/src/routes/{self.id}/+page.svelte", "w") as f:
            f.write(self._to_svelte())

        # TODO: Should rebuild the app here.
        # OR pass in --watch to vite build

    def _remove_svelte(self):
        # Remove all SvelteKit routes
        os.remove(f"{APP_DIR}/src/routes/{self.id}/+page.svelte")
        os.rmdir(f"{APP_DIR}/src/routes/{self.id}")

        # Remove all component wrappers
        for component_name in self.component.get_components():
            os.remove(f"{APP_DIR}/src/lib/wrappers/{self.id}/{component_name}.svelte")
        os.rmdir(f"{APP_DIR}/src/lib/wrappers/{self.id}")

    def get(self, id: str):
        try:
            from meerkat.state import state

            interface = state.identifiables.get(id, "interfaces")
        except KeyError:
            raise HTTPException(
                status_code=404, detail="No interface with id {}".format(id)
            )
        return interface

    def launch(self, return_url: bool = False):
        from meerkat.interactive.startup import is_notebook, output_startup_message

        if state.network_info is None:
            raise ValueError(
                "Interactive mode not initialized."
                "Run `network = mk.gui.start()` first."
            )

        if state.network_info.shareable_npm_server_name is not None:
            url = f"{state.network_info.shareable_npm_server_url}/{self.id}"
        else:
            url = f"{state.network_info.npm_server_url}/{self.id}"

        if return_url:
            return url
        if is_notebook():
            return IFrame(url, width=self.width, height=self.height)
        else:
            import webbrowser

            webbrowser.open(url)

            output_startup_message(url=url)

            # get locals of the main module when running in script.
            import __main__

            code.interact(local=__main__.__dict__)

    @property
    def frontend(self):
        return InterfaceFrontend(name=self.name, component=self.component.frontend)
