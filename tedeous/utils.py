"""this one contain some stuff for computing different auxiliary things."""

from typing import Tuple, List
from torch.nn import Module
from SALib import ProblemSpec
import numpy as np
import torch

def create_random_fn(eps: float) -> callable:
    """ Create random tensors to add some variance to torch neural network.

    Args:
        eps (float): randomize parameter.

    Returns:
        callable: creating random params function.
    """
    def randomize_params(m):
        if isinstance(m, torch.nn.Linear) or isinstance(m, torch.nn.Conv2d):
            m.weight.data = m.weight.data + \
                            (2 * torch.randn(m.weight.size()) - 1) * eps
            m.bias.data = m.bias.data + (2 * torch.randn(m.bias.size()) - 1) * eps

    return randomize_params

def samples_count(second_order_interactions: bool,
                  sampling_N: int,
                  op_length: list,
                  bval_length:list) -> Tuple[int, int]:
    """ Count samples for variance based sensitivity analysis.

    Args:
        second_order_interactions (bool): Calculate second-order sensitivities.
        sampling_N (int): essentially determines how often the lambda will be re-evaluated.
        op_length (list): operator values length.
        bval_length (list): boundary value length.

    Returns:
        sampling_amount (int): overall sampling value.
        sampling_D (int): sum of length of grid and boundaries.
    """

    grid_len = sum(op_length)
    bval_len = sum(bval_length)

    sampling_D = grid_len + bval_len

    if second_order_interactions:
        sampling_amount = sampling_N * (2 * sampling_D + 2)
    else:
        sampling_amount = sampling_N * (sampling_D + 2)
    return sampling_amount, sampling_D

def lambda_print(lam: torch.Tensor, keys: List) -> None:
    """ Print lambda value.

    Args:
        lam (torch.Tensor): lambdas values.
        keys (List): types of lambdas.
    """

    lam = lam.reshape(-1)
    for val, key in zip(lam, keys):
        print('lambda_{}: {}'.format(key, val.item()))

def bcs_reshape(
    bval: torch.Tensor,
    true_bval: torch.Tensor,
    bval_length: List) -> Tuple[dict, dict, dict, dict]:
    """ Preprocessing for lambda evaluating.

    Args:
        bval (torch.Tensor): matrix, where each column is predicted
                      boundary values of one boundary type.
        true_bval (torch.Tensor): matrix, where each column is true
                            boundary values of one boundary type.
        bval_length (list): list of length of each boundary type column.

    Returns:
        torch.Tensor: vector of difference between bval and true_bval.
    """

    bval_diff = bval - true_bval

    bcs = torch.cat([bval_diff[0:bval_length[i], i].reshape(-1)
                                        for i in range(bval_diff.shape[-1])])

    return bcs


class PadTransform(Module):
    """Pad tensor to a fixed length with given padding value.
    
    src: https://pytorch.org/text/stable/transforms.html#torchtext.transforms.PadTransform
    
    Done to avoid torchtext dependency (we need only this function).
    """

    def __init__(self, max_length: int, pad_value: int) -> None:
        """_summary_

        Args:
            max_length (int): Maximum length to pad to.
            pad_value (int):  Value to pad the tensor with.
        """
        super().__init__()
        self.max_length = max_length
        self.pad_value = float(pad_value)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """ Tensor padding

        Args:
            x (torch.Tensor): tensor for padding.

        Returns:
            torch.Tensor: filled tensor with pad value.
        """

        max_encoded_length = x.size(-1)
        if max_encoded_length < self.max_length:
            pad_amount = self.max_length - max_encoded_length
            x = torch.nn.functional.pad(x, (0, pad_amount), value=self.pad_value)
        return x
