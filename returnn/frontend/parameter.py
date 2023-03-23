"""
Parameter / variable
"""

from __future__ import annotations
from typing import Optional, Sequence
from returnn.tensor import Tensor, Dim
import returnn.frontend as rf
from ._backend import global_backend as _global_backend


__all__ = ["Parameter"]


class Parameter(Tensor):
    """
    This represents a (potential trainable) parameter,
    aka ``tf.Variable`` in TensorFlow,
    wrapping to ``VariableLayer`` in RETURNN.
    """

    def __init__(
        self,
        dims: Sequence[Dim],
        dtype: Optional[str] = None,
        *,
        sparse_dim: Optional[Dim] = None,
        trainable: Optional[bool] = None,
        auxiliary: bool = False,
        non_critical_for_restore: bool = False,
        weight_decay: Optional[float] = 0.0,
        initial: Optional[rf.init.ParamInitType] = None,
    ):
        """
        :param dims:
        :param dtype:
        :param sparse_dim:
        :param trainable: if True, and optimizer would do updates to this parameter in training mode
        :param auxiliary: if True, this indicates that this parameter should not be transformed by transformations
          such as weight normalization. One example are running statistics, as used for batch normalization.
          This usually implies that the parameter is not trainable, i.e. not to be updated by the optimizer,
          but usually has some custom update.
          This flag is not passed on to RETURNN but just used here for returnn-common logic.
        :param non_critical_for_restore: if True, this parameter is not critical for restoring a model.
        :param weight_decay:
        :param initial:
        """
        if not all(isinstance(dim, Dim) for dim in dims):
            raise TypeError(f"shape {dims} must be a sequence of Dim")
        if not all(isinstance(dim.dimension, int) for dim in dims):
            raise ValueError(f"shape {dims} must be static")
        if len(dims) != len(set((d, d.match_priority) for d in dims)):
            raise ValueError(f"shape {dims} dims must be unique")
        super(Parameter, self).__init__(
            "parameter",
            dims=dims,
            dtype=dtype or (rf.get_default_float_dtype() if not sparse_dim else rf.get_default_array_index_dtype()),
            sparse_dim=sparse_dim,
        )
        self.raw_tensor = _global_backend.create_parameter(self)
        if auxiliary and trainable is None:
            trainable = False
        self._trainable = trainable
        self._auxiliary = auxiliary
        self._non_critical_for_restore = non_critical_for_restore
        self._weight_decay = weight_decay
        self._initial = initial

    def __copy__(self):
        # Should return new copy. https://github.com/rwth-i6/returnn_common/pull/215#issuecomment-1269651064
        # Note that the values are *not* copied, but rather it will use the same param init scheme.
        res = type(self)(
            dims=self.dims,
            dtype=self.dtype,
            trainable=self.trainable,
            auxiliary=self.auxiliary,
            non_critical_for_restore=self.non_critical_for_restore,
            weight_decay=self.weight_decay,
        )
        res.initial = self.initial
        return res

    def __deepcopy__(self, memo=None):
        # Should return new copy. https://github.com/rwth-i6/returnn_common/pull/215#issuecomment-1269651064
        # Note that the values are *not* copied, but rather it will use the same param init scheme.
        from copy import deepcopy

        res = self.__copy__()
        if isinstance(self.initial, rf.init.ParamInit):
            res.initial = deepcopy(self.initial, memo=memo)  # noqa
        else:
            res.initial = self.initial
        return res

    @property
    def initial(self) -> Optional[rf.init.ParamInitType]:
        """initial value of the parameter"""
        return self._initial

    @initial.setter
    def initial(self, value: Optional[rf.init.ParamInitType]):
        # Keep the original ParamInit, so that copies of the Parameter would have a different initial random value.
        # https://github.com/rwth-i6/returnn_common/issues/216
        self._initial = value

    @property
    def weight_decay(self) -> float:
        """
        Weight decay, which is equivalent to L2 loss on the parameters for SGD.
        On RETURNN side, whether this is handled separately or is part of the main loss,
        can be controlled via the ``decouple_constraints`` config option.
        https://github.com/rwth-i6/returnn_common/issues/59#issuecomment-1073913421
        """
        return self._weight_decay or 0.0

    @weight_decay.setter
    def weight_decay(self, value: Optional[float]):
        self._weight_decay = value

    @property
    def trainable(self) -> Optional[bool]:
        """trainable"""
        return self._trainable

    @trainable.setter
    def trainable(self, value: Optional[bool]):
        self._trainable = value

    @property
    def auxiliary(self) -> bool:
        """auxiliary"""
        return self._auxiliary

    @auxiliary.setter
    def auxiliary(self, value: bool):
        self._auxiliary = value

    @property
    def non_critical_for_restore(self) -> bool:
        """non_critical_for_restore"""
        return self._non_critical_for_restore

    @non_critical_for_restore.setter
    def non_critical_for_restore(self, value: bool):
        self._non_critical_for_restore = value