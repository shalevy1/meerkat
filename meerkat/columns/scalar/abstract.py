from __future__ import annotations
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, List, Tuple, Union

import numpy as np
import pandas as pd
import pyarrow as pa

from meerkat.block.abstract import BlockView
from meerkat.block.arrow_block import ArrowBlock
from meerkat.block.pandas_block import PandasBlock
from meerkat.tools.lazy_loader import LazyLoader

from ..abstract import Column

torch = LazyLoader("torch")

if TYPE_CHECKING:
    import torch

ScalarColumnTypes = Union[np.ndarray, "torch.TensorType", pd.Series, List]


class ScalarColumn(Column):
    def __new__(cls, data: ScalarColumnTypes = None, backend: str = None):
        from .arrow import ArrowScalarColumn
        from .pandas import PandasScalarColumn

        if (cls is not ScalarColumn) or (data is None):
            return super().__new__(cls)

        backends = {"arrow": ArrowScalarColumn, "pandas": PandasScalarColumn}
        if backend is not None:
            if backend not in backends:
                raise ValueError(
                    f"Cannot create `ScalarColumn` with backend '{backend}'. "
                    f"Expected one of {list(backends.keys())}"
                )
            else:
                return super().__new__(backends[backend])

        if isinstance(data, BlockView):
            if isinstance(data.block, PandasBlock):
                return super().__new__(PandasScalarColumn)
            elif isinstance(data.block, ArrowBlock):
                return super().__new__(ArrowScalarColumn)

        if isinstance(data, (np.ndarray, torch.TensorType, pd.Series, List, Tuple)):
            return super().__new__(PandasScalarColumn)
        elif isinstance(data, pa.Array):
            return super().__new__(ArrowScalarColumn)
        else:
            raise ValueError(
                f"Cannot create `ScalarColumn` from object of type {type(data)}."
            )

    # compute functions
    @abstractmethod
    def _dispatch_aggregation_function(self, compute_fn: str, **kwargs):
        raise NotImplementedError()

    def mean(self, skipna: bool = True, **kwargs) -> float:
        return self._dispatch_aggregation_function("mean", skipna=skipna, **kwargs)

    def median(self, skipna: bool = True, **kwargs) -> Any:
        return self._dispatch_aggregation_function("median", skipna=skipna, **kwargs)

    def mode(self, **kwargs) -> ScalarColumn:
        return self._dispatch_aggregation_function("mode", **kwargs)
    
    def var(self, ddof: int = 1, **kwargs) -> ScalarColumn:
        return self._dispatch_aggregation_function("var", ddof=ddof, **kwargs)
    
    def std(self, ddof: int = 1, **kwargs) -> ScalarColumn:
        return self._dispatch_aggregation_function("std", ddof=ddof, **kwargs)

    def min(self, skipna: bool = True, **kwargs) -> ScalarColumn:
        return self._dispatch_aggregation_function("min", skipna=skipna, **kwargs)
    
    def max(self, skipna: bool = True, **kwargs) -> ScalarColumn:
        return self._dispatch_aggregation_function("max", skipna=skipna, **kwargs)
    
    def sum(self, skipna: bool = True, **kwargs) -> Any:
        return self._dispatch_aggregation_function("sum", skipna=skipna, **kwargs)

    def product(self, skipna: bool = True, **kwargs) -> Any:
        return self._dispatch_aggregation_function("product", skipna=skipna, **kwargs)

    def any(self, skipna: bool = True, **kwargs) -> Any:
        return self._dispatch_aggregation_function("any", skipna=skipna, **kwargs)

    def all(self, skipna: bool = True, **kwargs) -> Any:
        return self._dispatch_aggregation_function("all", skipna=skipna, **kwargs)