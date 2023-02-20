import base64
from io import BytesIO
from typing import Any, Dict, Tuple, Union

from meerkat.columns.deferred.base import DeferredCell
from meerkat.interactive.app.src.lib.component.abstract import Component
from meerkat.interactive.formatter.base import Formatter, FormatterGroup


class Image(Component):
    data: str
    classes: str = ""


class ImageFormatter(Formatter):
    component_class = Image
    data_prop: str = "data"

    def __init__(self, max_size: Tuple[int] = None, classes: str = ""):
        self.max_size = max_size
        self.classes = classes

    def encode(self, cell: Image) -> str:
        with BytesIO() as buffer:
            if self.max_size:
                cell.thumbnail(self.max_size)
            cell.save(buffer, "jpeg")
            return "data:image/jpeg;base64,{im_base_64}".format(
                im_base_64=base64.b64encode(buffer.getvalue()).decode()
            )

    @property
    def props(self) -> Dict[str, Any]:
        return {"classes": self.classes}

    def html(self, cell: Image) -> str:
        encoded = self.encode(cell, thumbnail=True)
        return f'<img src="{encoded}">'

    def _get_state(self) -> Dict[str, Any]:
        return {
            "max_size": self.max_size,
            "classes": self.classes,
        }

    def _set_state(self, state: Dict[str, Any]):
        self.max_size = state["max_size"]
        self.classes = state["classes"]


class ImageFormatterGroup(FormatterGroup):
    def __init__(self, classes: str = ""):
        super().__init__(
            base=ImageFormatter(classes=classes),
            thumbnail=ImageFormatter(max_size=[256, 256], classes=classes),
            full_screen=ImageFormatter(classes=classes),
        )


class DeferredImageFormatter(ImageFormatter):
    component_class: type = Image
    data_prop: str = "data"

    def encode(self, image: DeferredCell, thumbnail: bool = False) -> str:
        if image.absolute_path.startswith("http"):
            return image.absolute_path
        else:
            image = image()
            return super()._encode(image, thumbnail=thumbnail)
