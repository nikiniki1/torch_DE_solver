"""Module for connecting *eval.py*, *losses.py*"""

from __future__ import annotations

from copy import deepcopy
from typing import Tuple, Union, Any
import torch


from tedeous.points_type import Points_type
from tedeous.eval import Operator, Bounds
from tedeous.losses import Losses
from tedeous.device import device_type, check_device
from tedeous.input_preprocessing import lambda_prepare, Equation_NN, Equation_mat, Equation_autograd
from tedeous.utils import bcs_reshape, samples_count, Lambda, lambda_print


flatten_list = lambda t: [item for sublist in t for item in sublist]

class Solution():
    """
    class for different loss functions calculation.
    """
    def __init__(
        self,
        grid: torch.Tensor,
        equal_cls: Union[Equation_NN, Equation_mat, Equation_autograd],
        model: Union[torch.nn.Sequential, torch.Tensor],
        mode: str,
        weak_form: Union[None, list[callable]],
        lambda_operator,
        lambda_bound,
        tol: float = 0,
        derivative_points: int = 2):
        """
        Args:
            grid (torch.Tensor): discretization of comp-l domain.
            equal_cls (Union[Equation_NN, Equation_mat, Equation_autograd]): Equation_{NN, mat, autograd} object.
            model (Union[torch.nn.Sequential, torch.Tensor]): model of *mat or NN or autograd* mode.
            mode (str): *mat or NN or autograd*
            weak_form (Union[None, list[callable]]): list with basis functions, if the form is *weak*.
            lambda_operator (_type_): regularization parameter for operator term in loss.
            lambda_bound (_type_): regularization parameter for boundary term in loss.
            tol (float, optional): penalty in *casual loss*. Defaults to 0.
            derivative_points (int, optional): points number for derivative calculation.
            For details to Derivative_mat class.. Defaults to 2.
        """

        self.grid = check_device(grid)
        if mode == 'NN':
            sorted_grid = Points_type(self.grid).grid_sort()
            self.n_t = len(sorted_grid['central'][:, 0].unique())
        elif mode == 'autograd':
            self.n_t = len(self.grid[:, 0].unique())
        elif mode == 'mat':
            self.n_t = grid.shape[1]
        equal_copy = deepcopy(equal_cls)
        prepared_operator = equal_copy.operator_prepare()
        self._operator_coeff(equal_cls, prepared_operator)
        prepared_bconds = equal_copy.bnd_prepare()
        self.model = model.to(device_type())
        self.mode = mode
        self.weak_form = weak_form
        self.lambda_operator = lambda_operator
        self.lambda_bound = lambda_bound
        self.tol = tol


        self.operator = Operator(self.grid, prepared_operator, self.model,
                                   self.mode, weak_form, derivative_points)
        self.boundary = Bounds(self.grid, prepared_bconds, self.model,
                                   self.mode, weak_form, derivative_points)

        self.loss_cls = Losses(self.mode, self.weak_form, self.n_t, self.tol)
        self.eps = 0
        self.op_list = []
        self.bval_list = []
        self.loss_list = []

    @staticmethod
    def _operator_coeff(equal_cls: Any, operator: list):
        """ Coefficient checking in operator.

        Args:
            equal_cls (Any): Equation_{NN, mat, autograd} object.
            operator (list): prepared operator (result of operator_prepare())
        """
        for i, _ in enumerate(operator):
            eq = operator[i]
            for key in eq.keys():
                if isinstance(eq[key]['coeff'], torch.Tensor):
                    try:
                        eq[key]['coeff'] = equal_cls.operator[i][key]['coeff'].to(device_type())
                    except:
                        eq[key]['coeff'] = equal_cls.operator[key]['coeff'].to(device_type())


    def evaluate(self,
                 second_order_interactions: bool = True,
                 sampling_N: int = 1,
                 lambda_update: bool = False,
                 save_graph: bool = True) -> Tuple[torch.Tensor, torch.Tensor]:
        """ Computes loss.

        Args:
            second_order_interactions (bool, optional): optimizer iteration
            (serves only for computing adaptive lambdas). Defaults to True.
            sampling_N (int, optional): parameter for accumulation of
            solutions (op, bcs). The more sampling_N, the more accurate the
            estimation of the variance (only for computing adaptive lambdas). Defaults to 1.
            lambda_update (bool, optional): update lambda or not. Defaults to False.
            save_graph (bool, optional): responsible for saving the computational graph. Defaults to True.

        Returns:
            Tuple[torch.Tensor, torch.Tensor]: loss
        """

        op = self.operator.operator_compute()
        bval, true_bval, bval_keys, bval_length = self.boundary.apply_bcs()

        self.lambda_operator = lambda_prepare(op, self.lambda_operator)
        self.lambda_bound = lambda_prepare(bval, self.lambda_bound)

        loss, loss_normalized = self.loss_cls.compute(op, bval, true_bval,
                                                      self.lambda_operator,
                                                      self.lambda_bound,
                                                      save_graph)

        if lambda_update:
            # TODO refactor this lambda thing to class or function.
            bcs = bcs_reshape(bval, true_bval, bval_length)
            op_length = [op.shape[0]]*op.shape[-1]

            self.op_list.append(torch.t(op).reshape(-1).cpu().detach().numpy())
            self.bval_list.append(bcs.cpu().detach().numpy())
            self.loss_list.append(float(loss_normalized.item()))

            sampling_amount, sampling_D = samples_count(
                        second_order_interactions = second_order_interactions,
                        sampling_N = sampling_N,
                        op_length=op_length,
                        bval_length = bval_length)

            if len(self.op_list) == sampling_amount:
                self.lambda_operator, self.lambda_bound = Lambda(
                                        self.op_list, self.bval_list,
                                        self.loss_list,
                                        second_order_interactions)\
                                        .update(op_length=op_length,
                                                bval_length=bval_length,
                                                sampling_D=sampling_D)
                self.op_list.clear()
                self.bval_list.clear()
                self.loss_list.clear()

                oper_keys = [f'eq_{i}' for i in range(len(op_length))]
                lambda_print(self.lambda_operator, oper_keys)
                lambda_print(self.lambda_bound, bval_keys)


        return loss, loss_normalized
