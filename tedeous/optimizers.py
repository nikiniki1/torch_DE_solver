"""Module for custom optimizers"""

from copy import copy
import math
import torch
import numpy as np
from torch.nn.utils import parameters_to_vector, vector_to_parameters
from tedeous.device import device_type


class PSO():
    """Custom PSO optimizer.
    """
    def __init__(
        self,
        pop_size=30,
        b=0.99,
        c1=8e-2,
        c2=5e-1,
        lr=0.,
        c_decrease=False,
        beta_1=0.99,
        beta_2=0.999,
        variance=1e-2,
        epsilon=1e-8

    ):
        """The Particle Swarm Optimizer class.

        Args:
            pop_size (int, optional): Population of the PSO swarm. Defaults to 30.
            b (float, optional): Inertia of the particles. Defaults to 0.99.
            c1 (float, optional): The *p-best* coeficient. Defaults to 0.08.
            c2 (float, optional): The *g-best* coeficient. Defaults to 0.5.
            c_decrease (bool, optional): Flag for update_pso_params method. Defautls to False.
            beta_1 (float, optional):
            beta_2 (float, optional):
            variance (float, optional): Variance parameter for swarm creation
            based on model. Defaults to 1e-2.
            lr (float, optional): Learning rate for gradient descent. Defaults to 0.00,
            so there wouldn't have any gradient-based optimization.
            epsilon (float, optional): 
        """
        self.pop_size = pop_size
        self.b = b
        self.c1 = c1
        self.c2 = c2
        self.c_decrease = c_decrease
        self.beta_1 = beta_1
        self.beta_2 = beta_2
        self.epsilon = epsilon
        self.lr = (
            lr * np.sqrt(1 - self.beta_2) / (1 - self.beta_1)
        )
        self.variance = variance
        self.name = "PSO"

        """other parameters are determined in param_init method"""
        self.model_shape = None
        self.sln_cls = None
        self.vec_shape = None
        self.swarm = None
        self.loss_swarm, self.grads_swarm = None, None
        self.p, self.f_p = None, None
        self.g_best = None
        self.v = None
        self.m1 = None
        self.m2 = None

    def params_to_vec(self) -> torch.Tensor:
        """ Method for converting model parameters (NN and autograd)
           or model values (mat) to vector

        Returns:
            torch.Tensor: model parameters/model values vector.
        """
        if self.sln_cls.mode != 'mat':
            vec = parameters_to_vector(self.sln_cls.model.parameters())
        else:
            self.model_shape = self.sln_cls.model.shape
            vec = self.sln_cls.model.reshape(-1)

        return vec

    def vec_to_params(self, vec: torch.Tensor) -> None:
        """Method for converting vector to model parameters (NN, autograd)
           or model values (mat)

        Args:
            vec (torch.Tensor): The particle of swarm. 
        """
        if self.sln_cls.mode != 'mat':
            vector_to_parameters(vec, self.sln_cls.model.parameters())
        else:
            self.sln_cls.model.data = vec.reshape(self.model_shape).data

    def param_init(self, sln_cls) -> None:
        """Method for additional class objects initializing.

        Args:
            sln_cls (Solution): Solution class object to get model and method for loss calculation.
        """
        self.sln_cls = sln_cls
        self.sln_cls.model.requires_grad_()
        vec_shape = self.params_to_vec().shape
        self.vec_shape = list(vec_shape)[0]

        self.swarm = self.build_swarm()

        self.loss_swarm, self.grads_swarm = self.fitness_fn()

        self.p, self.f_p = copy(self.swarm).detach(), copy(self.loss_swarm).detach()

        self.g_best = self.p[torch.argmin(self.f_p)]
        self.v = self.start_velocities()
        self.m1 = torch.zeros(self.pop_size, self.vec_shape)
        self.m2 = torch.zeros(self.pop_size, self.vec_shape)

    def build_swarm(self):
        """Creates the swarm based on solution class model.

        Returns:
            torch.Tensor: The PSO swarm population.
            Each particle represents a neural network (NN, autograd) or model values (mat).
        """
        vector = self.params_to_vec()
        matrix = []
        for _ in range(self.pop_size):
            matrix.append(vector.reshape(1,-1))
        matrix = torch.cat(matrix)
        variance = torch.FloatTensor(self.pop_size, self.vec_shape).uniform_(
                                            self.variance, self.variance).to(device_type())
        swarm = (matrix + variance).clone().detach().requires_grad_(True)
        return swarm

    def update_pso_params(self) -> None:
        """Method for updating pso parameters if c_decrease=True.
        """
        self.c1 = self.c1 - 2 * self.c1 / self.n_iter
        self.c2 = self.c2 + self.c2 / self.n_iter

    def start_velocities(self) -> torch.Tensor:
        """Start the velocities of each particle in the population (swarm) as `0`.

        Returns:
            torch.Tensor: The starting velocities.
        """
        return torch.zeros((self.pop_size, self.vec_shape))

    def gradient(self, loss: torch.Tensor) -> torch.Tensor:
        """ Calculation of loss gradient by model parameters (NN, autograd)
            or model values (mat).

        Args:
            loss (torch.Tensor): result of loss calculation.

        Returns:
            torch.Tensor: calculated gradient vector.
        """
        if self.sln_cls.mode != 'mat':
            dl_dparam = torch.autograd.grad(loss, self.sln_cls.model.parameters())
        else:
            dl_dparam = torch.autograd.grad(loss, self.sln_cls.model)

        grads = parameters_to_vector(dl_dparam)

        return grads

    def loss_grads(self) -> tuple(torch.Tensor, torch.Tensor):
        """ Method for loss and gradient calculaation.
            It uses sln_cls.evaluate method for loss calc-n and
            gradient method for 'gradient' calc-n.

        Returns:
            tuple(torch.Tensor, torch.Tensor): calculated loss and gradient
        """
        loss, _ = self.sln_cls.evaluate()
        grads = self.gradient(loss)
        grads = torch.where(math.isnan(grads), torch.zeros_like(grads), grads)
        return loss, grads

    def fitness_fn(self) -> tuple(torch.Tensor, torch.Tensor):
        """Fitness function for the whole swarm.

        Returns:
            tuple(torch.Tensor, torch.Tensor): the losses and gradients for all particles.
        """
        loss_swarm = []
        grads_swarm = []
        for particle in self.swarm:
            self.vec_to_params(particle)
            loss_particle, grads = self.loss_grads()
            loss_swarm.append(loss_particle)
            grads_swarm.append(grads.reshape(1,-1))

        losses = torch.stack(loss_swarm).reshape(-1)
        gradients = torch.vstack(grads_swarm)
        return losses, gradients

    def get_randoms(self) -> torch.Tensor:
        """Generate random values to update the particles' positions.

        Returns:
            torch.Tensor: random tensor
        """
        return torch.rand((2, 1, self.vec_shape))

    def update_p_best(self) -> None:
        """Updates the *p-best* positions."""

        idx = torch.where(self.loss_swarm < self.f_p)

        self.p[idx] = self.swarm[idx]
        self.f_p[idx] = self.loss_swarm[idx]

    def update_g_best(self) -> None:
        """Update the *g-best* position."""
        self.g_best = self.p[torch.argmin(self.f_p)]

    def gradient_descent(self) -> torch.Tensor:
        """

        Returns:
            torch.Tensor: _description_
        """
        self.m1 = self.beta_1 * self.m1 + (1 - self.beta_1) * self.grads_swarm
        self.m2 = self.beta_2 * self.m2 + (1 - self.beta_2) * torch.square(
            self.grads_swarm)
        return self.lr * self.m1 / torch.sqrt(self.m2) + self.epsilon

    def step(self) -> torch.Tensor:
        """ It runs ONE step on the particle swarm optimization.

        Returns:
            torch.Tensor: loss value for best particle of thw swarm.
        """
        r1, r2 = self.get_randoms()

        self.v = self.b * self.v + (1 - self.b) * (
            self.c1 * r1 * (self.p - self.swarm) + self.c2 * r2 * (self.g_best - self.swarm)
        )
        self.swarm = self.swarm + self.v - self.gradient_descent()
        self.loss_swarm, self.grads_swarm = self.fitness_fn()
        self.update_p_best()
        self.update_g_best()
        self.vec_to_params(self.g_best)

        min_loss = min(self.f_p)

        return min_loss