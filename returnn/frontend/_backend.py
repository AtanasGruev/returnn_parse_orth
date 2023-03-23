"""
Backends for the frontend API
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Any, Union, TypeVar, Generic, Type, Sequence, Dict, Tuple
import contextlib

from returnn.util.basic import NotSpecified

if TYPE_CHECKING:
    from returnn.tensor import Tensor, Dim
    from .types import RawTensorTypes

T = TypeVar("T")  # tf.Tensor, torch.Tensor or so
T2 = TypeVar("T2")


class Backend(Generic[T]):
    """
    Abstract base class for the backend, operating on tensor type T, i.e. :class:`Tensor[T]`.

    This class and instances do not have any state,
    and all functions are staticmethod (or classmethod).
    """

    # class attribs set by derived classes
    RawTensorType: Type[T]
    is_tensorflow: bool = False  # whether this framework uses TensorFlow

    def __init__(self):
        raise Exception("do not instantiate this class")

    # --- some functions which provide some reasonable default implementation

    @classmethod
    def mark_as_default_output(cls, tensor: Tensor, *, shape: Optional[Sequence[int]] = None) -> None:
        """
        Calls mark_as_output(tensor, "output", shape=shape).

        :param tensor:
        :param shape: see :func:`mark_as_output`
        """
        cls.mark_as_output(tensor, "output", shape=shape)

    # --- functions to override

    @staticmethod
    def get_dtype_name_raw(raw_tensor: T) -> str:
        """
        :return: dtype of raw tensor, as string
        """
        raise NotImplementedError

    @staticmethod
    def as_dtype_raw(dtype_name: str) -> Any:
        """
        :param dtype_name: e.g. "float32"
        :return: dtype object
        """
        raise NotImplementedError

    @staticmethod
    def get_ndim_raw(raw_tensor: T) -> int:
        """
        :return: ndim of raw tensor. assumes it is known
        """
        raise NotImplementedError

    @staticmethod
    def get_shape_raw(raw_tensor: T) -> T:
        """
        :return: shape of raw tensor
        """
        raise NotImplementedError

    @staticmethod
    def get_shape_tuple_raw(raw_tensor: T) -> Tuple[Union[int, T]]:
        """
        :return: shape of raw tensor. assumes that ndim is known.
            In eager frameworks, all dims are int.
        """
        raise NotImplementedError

    @staticmethod
    def get_known_shape_raw(raw_tensor: T) -> Tuple[Optional[int]]:
        """
        :return: shape of raw tensor, int for static known, None otherwise. assumes that ndim is known.
            This will not create any ops.
            In eager frameworks, all dims are known.
        """
        raise NotImplementedError

    @staticmethod
    def set_known_shape_raw(raw_tensor: T, shape: Tuple[Optional[int]]) -> None:
        """
        Sets the known shape of the raw tensor.
        This is only supported in graph-based frameworks,
        and just performs a check in eager frameworks.
        """
        # Default implementation for eager-based frameworks.
        backend = get_backend_by_raw_tensor_type(type(raw_tensor))
        existing_shape = backend.get_known_shape_raw(raw_tensor)
        assert all(dim is not None for dim in existing_shape)
        assert len(shape) == len(existing_shape)
        assert all(dim is None or dim == existing_shape[i] for i, dim in enumerate(shape))

    @staticmethod
    def fill_raw(shape: Union[Sequence[Union[int, T]], T], value: Union[Any, T]) -> T:
        """
        :param shape: shape
        :param value: scalar value to fill
        :return: raw tensor filled with value everywhere
        """
        raise NotImplementedError

    @staticmethod
    def compare_raw(a: T, kind: str, b: T) -> T:
        """
        :param a:
        :param kind: "equal"|"==", "less"|"<", "less_equal"|"<=", "greater"|">", "greater_equal"|">=", "not_equal"|"!="
        :param b:
        :return: a `kind` b
        """
        raise NotImplementedError

    @staticmethod
    def combine_raw(a: T, kind: str, b: T) -> T:
        """
        :param a:
        :param kind: "add"|"+", "sub"|"-", "mul"|"*", "truediv"|"/", "floordiv"|"//", "mod"|"%", "pow"|"**",
            "max"|"maximum", "min"|"minimum", "logical_and", "logical_or", "squared_difference"
        :param b:
        :return: a `kind` b
        """
        raise NotImplementedError

    @staticmethod
    def reshape_raw(raw_tensor: T, shape: Union[Sequence[Union[int, T]], T]) -> T:
        """
        :param raw_tensor: raw tensor
        :param shape: new shape
        :return: reshaped raw tensor
        """
        raise NotImplementedError

    @classmethod
    def squeeze_raw(cls, raw_tensor: T, axes: Sequence[int]) -> T:
        """
        :param raw_tensor: raw tensor
        :param axes: axes to squeeze
        :return: squeezed raw tensor
        """
        # Default implementation using reshape_raw.
        known_shape = cls.get_known_shape_raw(raw_tensor)
        assert all([known_shape[axis] == 1 for axis in axes])
        new_shape = [dim for a, dim in enumerate(cls.get_shape_tuple_raw(raw_tensor)) if a not in axes]
        return cls.reshape_raw(raw_tensor, new_shape)

    @staticmethod
    def transpose_raw(raw_tensor: T, perm: Sequence[int]) -> T:
        """
        :param raw_tensor: raw tensor
        :param perm: permutation
        :return: transposed raw tensor
        """
        raise NotImplementedError

    @staticmethod
    def expand_dims_raw(raw_tensor: T, axis: int) -> T:
        """
        :param raw_tensor:
        :param axis:
        :return: raw tensor with new axis
        """
        raise NotImplementedError

    @staticmethod
    def expand_raw(raw_tensor: T, axis: int, dim: Union[int, T]) -> T:
        """
        :param raw_tensor:
        :param axis: shape[axis] must be 1
        :param dim: the new dim for shape[axis]
        :return: shape[axis] expands to dim.
            in PyTorch or other frameworks which support custom strides,
            this is an efficient view and not a copy.
        """
        raise NotImplementedError

    # Restrict the possible activation function names,
    # to not get unexpected behavior,
    # or unwanted incompatibilities.
    _AllowedActivationFuncs = {
        "exp",
        "expm1",
        "log",
        "log1p",
        "sqrt",
        "rsqrt",
        "square",
        "abs",
        "tanh",
        "sigmoid",
        "log_sigmoid",
        "sin",
        "cos",
        "ceil",
        "floor",
        "round",
        "relu",
        "elu",
        "selu",
        "silu",
        "logical_not",
        "neg",
    }

    @staticmethod
    def activation_raw(raw_tensor: T, func: str) -> T:
        """
        :param raw_tensor:
        :param func: "tanh", "sigmoid", "relu", ...
        :return: raw tensor with activation applied
        """
        raise NotImplementedError

    @staticmethod
    def softmax(tensor: Tensor, *, axis: Dim) -> Tensor:
        """
        :param tensor:
        :param axis:
        :return: softmax over axis
        """
        raise NotImplementedError

    @staticmethod
    def log_softmax(tensor: Tensor, *, axis: Dim) -> Tensor:
        """
        :param tensor:
        :param axis:
        :return: log_softmax over axis
        """
        raise NotImplementedError

    @staticmethod
    def sequence_mask_raw(lengths: T, *, batch_major: bool = True) -> T:
        """
        Like tf.sequence_mask().

        :param lengths: shape (batch,)
        :param batch_major:
        :return: tensor mask of shape (batch,maxlen) if batch_major else (maxlen,batch) of type bool
        """
        raise NotImplementedError

    @staticmethod
    @contextlib.contextmanager
    def name_scope_raw(name: str) -> Any:
        """
        Default implementation for eager-based frameworks:
        Do nothing, tensors do not have a name.

        :param name:
        :return: context manager
        """
        # Default implementation for eager-based frameworks
        pass  # nothing to do

    @staticmethod
    @contextlib.contextmanager
    def control_dependencies_raw(dependencies: Sequence[Any]) -> Any:
        """
        Default implementation for eager-based frameworks:
        Do nothing, we expect that the dependencies are already executed.

        :param dependencies: raw tensors or ops
        :return: context manager
        """
        # Default implementation for eager-based frameworks
        yield

    @staticmethod
    def identity_with_control_dependencies_raw(raw_tensor: T, dependencies: Sequence[Any]) -> T:
        """
        Default implementation for eager-based frameworks:
        Do nothing, we expect that the dependencies are already executed.

        :param raw_tensor: raw tensor
        :param dependencies: raw tensors or ops
        :return: raw tensor
        """
        # Default implementation for eager-based frameworks
        return raw_tensor

    @staticmethod
    def create_placeholder(tensor: Tensor) -> T:
        """
        :return: tf.placeholder in TF

        This is really only for TensorFlow for the deprecated option auto_create_placeholders
        and should not be used in other backends,
        even in graph-based backends.
        Rather, the logic to create placeholders should be done elsewhere.
        """
        raise Exception("create_placeholder not supported by backend")

    @staticmethod
    def create_parameter(tensor: Tensor) -> T:
        """
        :return: parameter
        """
        raise NotImplementedError

    @staticmethod
    def runtime_sanity_checks(tensor: Tensor) -> Any:
        """
        Checks whether the tensor.raw_tensor is consistent with the tensor metadata.

        In graph-based frameworks (TF graph), we return some operation here.
        In eager frameworks, we would not return anything but instead directly perform the checks.
        """
        # By default, we do not do any checks. This is optional for the backend.
        pass

    @staticmethod
    def is_valid_in_current_graph(tensor: Tensor) -> bool:
        """
        :return: whether the raw tensor is valid in the current graph.
            In eager-mode frameworks, this is always true -- there is no graph.
        """
        return True

    @staticmethod
    def format_graph_output(raw_tensor: T, *, max_depth: Optional[int] = None) -> str:
        """
        :return: the computation graph leading to this tensor formatted.
            In eager-mode frameworks, this is not supported and returns None.
        """
        return "<no-graph>"

    @staticmethod
    def mark_as_loss(
        loss: Tensor,
        name: str,
        *,
        scale: Optional[float] = 1.0,
        as_error: bool = False,
        use_normalized_loss: bool = False,
        use_flatten_frames: bool = True,
        custom_inv_norm_factor: Optional[Tensor] = None,
    ) -> None:
        """
        Mark the given loss tensor as a loss.
        This has the effect that it is specially handled by RETURNN.
        Specifically, the optimizer can use it in training,
        and it is used for reporting per batch or per epoch,
        and for learning rate scheduling.

        This currently uses :class:`AsIsLoss` in RETURNN
        but this is an implementation detail and might change.

        :param loss:
        :param name: name of the loss. this name is used for reporting by RETURNN, and also for LR scheduling.
        :param scale: scale the loss by this factor for the training optimizer
          (but not for any reporting). setting to 0.0 has the effect that this loss is not used by the optimizer.
        :param as_error: if True, this loss is reported as an error instead of a loss,
          and not used by the training optimizer.
          This is by convention sth like the frame-error or edit-distance, and usually not differentiable anyway.
        :param bool use_flatten_frames: If True, will use :func:`returnn.tf.util.basic.flatten_with_seq_len_mask`,
          i.e. a "packed" sequence with the padded frames removed, and accumulates over that.
          This can be more efficient, also because it will further optimize incoming computations
          and e.g. skip softmax computations right before on the padded frames.
          This can also avoid issues with inf/nan in some cases.
          If False, it will mask the loss to 0 in the padded frames and accumulate over that.
          Typically, setting this to True (default) is both more efficient and better.
        :param bool use_normalized_loss: the loss used in optimization will be normalized.
          E.g. if the overall normalization is sum(loss)/sum(num_frames), this is also what the optimizer will use,
          otherwise the optimizer will just use sum(loss).
        :param custom_inv_norm_factor:
          The standard norm factor is 1/sum(target_seq_len) if the target has a time-axis,
          or 1/sum(output_seq_len) if there is no target and the output has a time-axis,
          or 1 otherwise. (See :func:`Loss.init` for details.)
          This is used for proper normalization of accumulated loss/error per epoch
          and also proper normalization per batch for reporting,
          no matter if use_normalized_loss is True or False.
          If you want to change this norm factor, you can set this.
          Basically, for all reporting, it uses sum(loss) * sum(custom_inv_norm_factor).
        """
        raise NotImplementedError

    @staticmethod
    def mark_as_output(tensor: Tensor, name: str, *, shape: Optional[Sequence[int]] = None) -> None:
        """
        Mark this as an output.
        This has the effect that RETURNN will in any case construct the corresponding layer.
        Also see :func:`mark_as_default_output`.

        This is intended mostly for forwarding, or exporting the model (TF graph, TFLite, ONNX, etc).
        You must specify a shape to have the output shape (order of dims) well-defined
        (if not specified, we check if some defaults are possible, like BTF, or BF).

        :param tensor:
        :param name:
        :param shape: this specifies the order of the dims of the output, such that it is well-defined
            for some external application.
            If not specified, we try to infer BTF or BF as default, if that works, otherwise it will be an error.
        """
        raise NotImplementedError

    @staticmethod
    def convert_to_tensor(
        value: Union[Tensor, T, RawTensorTypes],
        *,
        dims: Sequence[Dim] = (),
        dtype: Optional[str] = None,
        sparse_dim: Optional[Dim] = None,
    ) -> Tensor[T]:
        """
        :param value: tensor, or scalar raw tensor or some other scalar value
        :param dims:
        :param dtype:
        :param sparse_dim:
        :return: tensor
        """
        raise NotImplementedError

    @staticmethod
    def full(
        dims: Sequence[Dim], fill_value: RawTensorTypes, *, dtype: str, sparse_dim: Optional[Dim] = None
    ) -> Tensor:
        """
        https://data-apis.org/array-api/latest/API_specification/generated/array_api.full.html

        :param dims:
        :param fill_value:
        :param dtype:
        :param sparse_dim:
        :return: tensor
        """
        raise NotImplementedError

    @staticmethod
    def matmul(a: Tensor[T], b: Tensor[T], *, reduce: Union[Dim, Sequence[Dim]]) -> Tensor[T]:
        """
        This performs a batched matmul of two sources a and b
        (non-batched matmul and dot product are special cases).
        The underlying operation is a batched matmul (shared..., I, J) * (shared..., J, K) -> (shared..., I, K).
        The inputs a and b are transformed internally into the required shapes in the following way:
        The axis J is specified via the Dim given as 'reduce'. If multiple reduce Dims are given the corresponding axes
        are merged into one before the matmul via a reshape. All other matching Dims in a and b will be treated as
        batch dimensions ('shared...'). Dims unique to a and b define the axes I and K, respectively. (Multiple or no
        unique axes in a and b are supported too.)

        Depending on which Dims exist in a, b and reduce this dot operation can be used to compute scaling, scalar
        product, outer product, matrix-vector multiplication, matrix-matrix multiplication etc. (all possibly batched).

        :param a:
        :param b:
        :param reduce: Dims over which to perform the product, have to be present in both a and b
        :return: result of dot product, Dim order: common axes as sorted in a, unique axes of a (in order),
            unique axes of b (in order)
        """
        raise NotImplementedError

    @staticmethod
    def range_over_dim(dim: Dim) -> Tensor[T]:
        """
        :param dim:
        :return: tensor with shape [dim]
        """
        raise NotImplementedError

    _AllowedReduceModes = {"sum", "max", "min", "mean", "logsumexp", "any", "all", "argmin", "argmax"}

    @staticmethod
    def reduce(
        source: Tensor[T],
        *,
        mode: str,
        axis: Union[Dim, Sequence[Dim]],
        use_time_mask: bool = NotSpecified,
    ) -> Tensor[T]:
        """
        Reduce the tensor along the given axis

        :param source:
        :param mode: "sum", "max", "min", "mean", "logsumexp", "any", "all", "argmin", "argmax"
        :param axis:
        :param use_time_mask: if True (default), use the time mask (part of dim tag) to ignore padding frames
        :return: tensor with axis removed
        """
        raise NotImplementedError


# We use a global instance, and we modify __class__ inplace,
# such that any reference to this can be updated.
# This is exposed to the user as `returnn.frontend`.
# The __class__ assignment is done in `select_engine`.
# Use object.__new__ because we disallow creating instances of Frontend.
global_backend = object.__new__(Backend)

_dispatch_table = {}  # type: Dict[Type, Type[Backend]]


def select_backend_returnn_layers_tf():
    """
    Selects the RETURNN layers backend (based on TF).
    """
    import tensorflow as tf

    backend = get_backend_by_raw_tensor_type(tf.Tensor)  # side-effect: register it
    global_backend.__class__ = backend

    # TODO returnn layer type, register_frontend_by_tensor_type for that
    #   global_frontend.__class__ = ReturnnLayersFrontend


def select_backend_torch():
    """
    Selects the PyTorch (low-level) backend.
    """
    import torch

    backend = get_backend_by_raw_tensor_type(torch.Tensor)  # side-effect: register it
    global_backend.__class__ = backend


def get_backend_by_tensor(tensor: Tensor, *, fallback: Optional[T2] = None) -> Union[Type[Backend[T]], T2]:
    """
    :param tensor:
    :param fallback:
    """
    if fallback and tensor.raw_tensor is None:
        return fallback
    assert tensor.raw_tensor is not None
    return get_backend_by_raw_tensor_type(type(tensor.raw_tensor))


def get_backend_by_raw_tensor_type(tensor_type: Type[T]) -> Union[Type[Backend[T]]]:
    """
    :param tensor_type:
    """
    if tensor_type not in _dispatch_table:
        # We don't register all possible subclasses in the dispatch table.
        # Check through the MRO.
        for type_ in tensor_type.__mro__:
            if type_ in _dispatch_table:
                # Also register it for faster future lookups.
                _dispatch_table[tensor_type] = _dispatch_table[type_]
                return _dispatch_table[type_]
    if tensor_type not in _dispatch_table:
        # It would be registered if there was any select_engine or select_backend_* call.
        # However, some code might not have done that, so for the common cases,
        # we do it here.
        if tensor_type.__module__.split(".")[0] == "tensorflow":
            from returnn.tf.frontend_low_level import TFBackend

            backend_type = TFBackend
            tensor_types = _get_tensor_types_tf()
        elif tensor_type.__module__.split(".")[0] == "torch":
            from returnn.torch.frontend import TorchBackend

            backend_type = TorchBackend
            tensor_types = _get_tensor_types_torch()
        else:
            raise Exception(f"unknown tensor type {tensor_type}")
        assert any(issubclass(tensor_type, type_) for type_ in tensor_types)
        for type_ in tensor_types:
            register_backend_by_tensor_type(type_, backend_type)
        return backend_type
    return _dispatch_table[tensor_type]


def register_backend_by_tensor_type(tensor_type: Type[T], backend: Type[Backend[T]]):
    """
    :param tensor_type:
    :param backend:
    """
    _dispatch_table[tensor_type] = backend


def _get_tensor_types_tf():
    """
    :return: tuple of relevant tensor types in TF.
        Note that it is not so important to cover all, as we also check issubclass as a fallback.
    """
    import tensorflow as tf

    ls = [tf.Tensor, tf.Variable]
    return tuple(ls)


def _get_tensor_types_torch():
    """
    :return: tuple of relevant tensor types in PyTorch.
        Note that it is not so important to cover all, as we also check issubclass as a fallback.
    """
    import torch

    ls = [torch.Tensor, torch.nn.Parameter]
    return tuple(ls)