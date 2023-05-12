"""
Provides the :class:`LSTM` module.
"""

from __future__ import annotations

from typing import Tuple, Sequence

import returnn.frontend as rf
from returnn.tensor import Tensor, Dim, single_step_dim


__all__ = ["LSTM", "LstmState", "ZoneoutLSTM"]


class LSTM(rf.Module):
    """
    LSTM module.
    """

    def __init__(
        self,
        in_dim: Dim,
        out_dim: Dim,
        *,
        with_bias: bool = True,
    ):
        """
        Code to initialize the LSTM module.
        """
        super().__init__()

        self.in_dim = in_dim
        self.out_dim = out_dim

        self.ff_weight = rf.Parameter((4 * self.out_dim, self.in_dim))
        self.ff_weight.initial = rf.init.Glorot()
        self.rec_weight = rf.Parameter((4 * self.out_dim, self.out_dim))
        self.rec_weight.initial = rf.init.Glorot()

        self.bias = None
        if with_bias:
            self.bias = rf.Parameter((4 * self.out_dim,))
            self.bias.initial = 0.0

    def __call__(self, source: Tensor, *, state: LstmState, spatial_dim: Dim) -> Tuple[Tensor, LstmState]:
        """
        Forward call of the LSTM.

        :param source: Tensor of size {...,in_dim} if spatial_dim is single_step_dim else {...,spatial_dim,in_dim}.
        :param state: State of the LSTM. Both h and c are of shape {...,out_dim}.
        :return: output of shape {...,out_dim} if spatial_dim is single_step_dim else {...,spatial_dim,out_dim},
            and new state of the LSTM.
        """
        if not state.h or not state.c:
            raise ValueError(f"{self}: state {state} needs attributes ``h`` (hidden) and ``c`` (cell).")
        if self.in_dim not in source.dims_set:
            raise ValueError(f"{self}: input {source} does not have in_dim {self.in_dim}")

        # noinspection PyProtectedMember
        result, new_state = source._raw_backend.lstm(
            source=source,
            state_c=state.c,
            state_h=state.h,
            ff_weight=self.ff_weight,
            rec_weight=self.rec_weight,
            bias=self.bias,
            spatial_dim=spatial_dim,
            in_dim=self.in_dim,
            out_dim=self.out_dim,
        )
        new_state = LstmState(*new_state)

        return result, new_state

    def default_initial_state(self, *, batch_dims: Sequence[Dim]) -> LstmState:
        """initial state"""
        return LstmState(
            h=rf.zeros(list(batch_dims) + [self.out_dim]),
            c=rf.zeros(list(batch_dims) + [self.out_dim]),
        )


class LstmState(rf.State):
    """LSTM state"""

    def __init__(self, h: Tensor, c: Tensor):
        super().__init__()
        self.h = h
        self.c = c


class ZoneoutLSTM(LSTM):
    """
    Zoneout LSTM module.
    """

    def __init__(
        self,
        in_dim: Dim,
        out_dim: Dim,
        *,
        with_bias: bool = True,
        zoneout_factor_cell: float = 0.0,
        zoneout_factor_output: float = 0.0,
        use_zoneout_output: bool = True,
        forget_bias: float = 0.0,
        parts_order: str = "ifco",
    ):
        """
        :param in_dim:
        :param out_dim:
        :param with_bias:
        :param zoneout_factor_cell: 0.0 is disabled. reasonable is 0.15.
        :param zoneout_factor_output: 0.0 is disabled. reasonable is 0.05.
        :param use_zoneout_output: True is like the original paper. False is like older RETURNN versions.
        :param forget_bias: 1.0 is default in RETURNN/TF ZoneoutLSTM.
            0.0 is default in :class:`LSTM`, or RETURNN NativeLSTM, PyTorch LSTM, etc.
        :param parts_order:
            i: input gate.
            f: forget gate.
            o: output gate.
            c|g|j: input.
            icfo: like RETURNN/TF ZoneoutLSTM.
            ifco: PyTorch (cuDNN) weights, standard for :class:`LSTM`.
            cifo: RETURNN NativeLstm2 weights.
        """
        super().__init__(
            in_dim,
            out_dim,
            with_bias=with_bias,
        )
        self.zoneout_factor_cell = zoneout_factor_cell
        self.zoneout_factor_output = zoneout_factor_output
        self.use_zoneout_output = use_zoneout_output
        self.forget_bias = forget_bias
        self.parts_order = parts_order.replace("c", "j").replace("g", "j")
        assert len(self.parts_order) == 4 and set(self.parts_order) == set("ijfo")

    def __call__(self, source: Tensor, *, state: LstmState, spatial_dim: Dim) -> Tuple[Tensor, LstmState]:
        """
        Forward call of the LSTM.

        :param source: Tensor of size {...,in_dim} if spatial_dim is single_step_dim else {...,spatial_dim,in_dim}.
        :param state: State of the LSTM. Both h and c are of shape {...,out_dim}.
        :return: output of shape {...,out_dim} if spatial_dim is single_step_dim else {...,spatial_dim,out_dim},
            and new state of the LSTM.
        """
        if not state.h or not state.c:
            raise ValueError(f"{self}: state {state} needs attributes ``h`` (hidden) and ``c`` (cell).")
        if self.in_dim not in source.dims_set:
            raise ValueError(f"{self}: input {source} does not have in_dim {self.in_dim}")

        if spatial_dim == single_step_dim:
            prev_c = state.c
            prev_h = state.h

            # Apply vanilla LSTM
            in_ = rf.dot(source, self.ff_weight, reduce=self.in_dim)
            rec = rf.dot(prev_h, self.rec_weight, reduce=self.out_dim)
            x = in_ + rec
            if self.bias is not None:
                x = x + self.bias
            parts = rf.split(x, axis=4 * self.out_dim, out_dims=[self.out_dim] * 4)
            parts = {k: v for k, v in zip(self.parts_order, parts)}
            i, j, f, o = parts["i"], parts["j"], parts["f"], parts["o"]

            new_c = rf.sigmoid(f + self.forget_bias) * prev_c + rf.sigmoid(i) * rf.tanh(j)
            new_h = rf.sigmoid(o) * rf.tanh(new_c)
            output = new_h

            # Now the ZoneoutLSTM part, which is optional (zoneout_factor_cell > 0 or zoneout_factor_output > 0).
            # It has different behavior depending on the train flag.
            is_training = rf.get_run_ctx().train_flag

            if self.zoneout_factor_cell > 0.0:
                c = rf.cond(
                    is_training,
                    lambda: (1 - self.zoneout_factor_cell)
                    * rf.dropout(new_c - prev_c, drop_prob=self.zoneout_factor_cell, axis=self.out_dim)
                    + prev_c,
                    lambda: (1 - self.zoneout_factor_cell) * new_c + self.zoneout_factor_cell * prev_c,
                )
            else:
                c = new_c

            if self.zoneout_factor_output > 0.0:
                h = rf.cond(
                    is_training,
                    lambda: (1 - self.zoneout_factor_output)
                    * rf.dropout(new_h - prev_h, drop_prob=self.zoneout_factor_output, axis=self.out_dim)
                    + prev_h,
                    lambda: (1 - self.zoneout_factor_output) * new_h + self.zoneout_factor_output * prev_h,
                )
            else:
                h = new_h

            new_state = LstmState(c=c, h=h)

            if self.use_zoneout_output:  # really the default, sane and original behavior
                output = h

            output.feature_dim = self.out_dim
            new_state.h.feature_dim = self.out_dim
            new_state.c.feature_dim = self.out_dim
            return output, new_state

        def _body(s, x_):
            y_, s = self(x_, state=s, spatial_dim=single_step_dim)
            return s, y_

        batch_dims = source.remaining_dims((spatial_dim, self.in_dim))
        new_state, output, _ = rf.scan(
            spatial_dim=spatial_dim,
            initial=state,
            xs=source,
            ys=Tensor("lstm-out", dims=batch_dims + [self.out_dim], dtype=source.dtype),
            body=_body,
        )
        return output, new_state
