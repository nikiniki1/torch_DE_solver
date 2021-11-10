import torch
import numpy as np
from input_preprocessing import grid_prepare, bnd_prepare, operator_prepare,batch_bconds_transform
from points_type import grid_sort

def take_derivative_shift_op(model, term):
    """
    Axiluary function serves for single differential operator resulting field
    derivation

    Parameters
    ----------
    model : torch.Sequential
        Neural network.
    term : TYPE
        differential operator in conventional form.

    Returns
    -------
    der_term : torch.Tensor
        resulting field, computed on a grid.

    """
    # it is may be int, function of grid or torch.Tensor
    coeff = term[0]
    # this one contains shifted grids (see input_preprocessing module)
    shift_grid_list = term[1]
    # signs corresponding to a grid
    s_order_norm_list = term[2]
    # float that represents power of the differential term
    power = term[3]
    # initially it is an ones field
    der_term = torch.zeros_like(model(shift_grid_list[0][0])) + 1
    for j, scheme in enumerate(shift_grid_list):
        # every shift in grid we should add with correspoiding sign, so we start
        # from zeros
        grid_sum = torch.zeros_like(model(scheme[0]))
        for k, grid in enumerate(scheme):
            # and add grid sequentially
            grid_sum += model(grid) * s_order_norm_list[j][k]
        # Here we want to apply differential operators for every term in the product
        der_term = der_term * grid_sum ** power[j]
    der_term = coeff * der_term
    return der_term


def apply_const_shift_operator(model, operator):
    """
    Deciphers equation in a single grid subset to a field.

    Parameters
    ----------
    model : torch.Sequential
        Neural network.
    operator : list
        Single (len(subset)==1) operator in input form. See 
        input_preprocessing.operator_prepare()

    Returns
    -------
    total : torch.Tensor

    """
    for term in operator:
        dif = take_derivative_shift_op(model, term)
        try:
            total += dif
        except NameError:
            total = dif
    return total


def apply_operator_set(model, operator_set):
    """
    Deciphers equation in a whole grid to a field.

    Parameters
    ----------
    model : torch.Sequential
        Neural network.
    operator : list
        Multiple (len(subset)>=1) operators in input form. See 
        input_preprocessing.operator_prepare()

    Returns
    -------
    total : torch.Tensor

    """
    field_part = []
    for operator in operator_set:
        field_part.append(apply_const_shift_operator(model, operator))
    field_part = torch.cat(field_part)
    return field_part


flatten_list = lambda t: [item for sublist in t for item in sublist]

def lp_norm(*arg,p=2,normalized=False,weighted=False):
    if weighted==True and len(arg)==1:
        print('No grid is passed, using non-weighted norm')
        weighted=False
    if len(arg)==2:
        grid=arg[0]
        mat=arg[1]
    elif len(arg)==1:
        mat=arg[0]
        grid=None
    else:
        print('Something went wrong, passed more than two arguments')
        return
    grid_prod=1
    if weighted:
        for i in range(grid.shape[-1]):
            grid_prod*=grid[:,i]
    if p>1: 
        if not weighted and not normalized:
             norm=torch.mean((mat) ** p)
        elif not weighted and normalized:
            norm=torch.pow(torch.mean((mat) ** p),1/p)
        elif weighted and not normalized:
            norm=torch.mean(grid_prod*(mat) ** p)
        elif weighted and normalized:
            norm=torch.pow(torch.mean(grid_prod*(mat) ** p),1/p)
    elif p==1:
        if not weighted:
             norm=torch.mean(torch.abs(mat))
        elif weighted:
            norm=torch.mean(grid_prod*torch.abs(mat))  
    return norm


def point_sort_shift_loss(model, grid, operator_set, bconds, lambda_bound=10,norm=None):

    op = apply_operator_set(model, operator_set)
    
    if bconds==None:
        loss = torch.mean((op) ** 2)
        return loss
    
    true_b_val_list = []
    b_val_list = []
    b_pos_list = []

    # we apply no  boundary conditions operators if they are all None

    simpleform = False
    for bcond in bconds:
        if bcond[1] == None:
            simpleform = True
        if bcond[1] != None:
            simpleform = False
            break
    if simpleform:
        for bcond in bconds:
            b_pos_list.append(bcond[0])
            true_boundary_val = bcond[2].reshape(-1, 1)
            true_b_val_list.append(true_boundary_val)
        # print(flatten_list(b_pos_list))
        # b_pos=torch.cat(b_pos_list)
        true_b_val = torch.cat(true_b_val_list)
        b_op_val = model(grid)
        b_val = b_op_val[flatten_list(b_pos_list)]
    # or apply differential operatorn first to compute corresponding field and
    else:
        for bcond in bconds:
            b_pos = bcond[0]
            b_pos_list.append(bcond[0])
            b_cond_operator = bcond[1]
            true_boundary_val = bcond[2].reshape(-1, 1)
            true_b_val_list.append(true_boundary_val)
            if b_cond_operator == None or b_cond_operator == [[1, [None], 1]]:
                b_op_val = model(grid)
            else:
                b_op_val = apply_operator_set(model, b_cond_operator)
            # take boundary values
            b_val_list.append(b_op_val[b_pos])
        true_b_val = torch.cat(true_b_val_list)
        b_val = torch.cat(b_val_list)

    """
    actually, we can use L2 norm for the operator and L1 for boundary
    since L2>L1 and thus, boundary values become not so signifnicant, 
    so the NN converges faster. On the other hand - boundary conditions is the
    crucial thing for all that stuff, so we should increase significance of the
    coundary conditions
    """
    # l1_lambda = 0.001
    # l1_norm =sum(p.abs().sum() for p in model.parameters())
    # loss = torch.mean((op) ** 2) + lambda_bound * torch.mean((b_val - true_b_val) ** 2)+ l1_lambda * l1_norm
    
    
    # loss = torch.mean((op) ** 2) + lambda_bound * torch.mean((b_val - true_b_val) ** 2)
    
    if norm==None:
        op_weigthed=False
        op_normalized=False
        op_p=2
        b_weigthed=False
        b_normalized=False
        b_p=2
    else:
        op_weigthed=norm['operator_weighted']
        op_normalized=norm['operator_normalized']
        op_p=norm['operator_p']
        b_weigthed=norm['boundary_weighted']
        b_normalized=norm['boundary_weighted']
        b_p=norm['boundary_p']
    
    loss = lp_norm(grid[:len(op)],op,weighted=op_weigthed,normalized=op_normalized,p=op_p) + \
    lambda_bound * lp_norm(grid[flatten_list(b_pos_list)],b_val - true_b_val,p=b_p,weighted=b_weigthed,normalized=b_normalized)
    
    return loss

def point_sort_shift_loss_batch(model, prepared_grid, point_type, operator, bconds,subset=['central'], lambda_bound=10,batch_size=32,h=0.001,norm=None):
    permutation = torch.randperm(prepared_grid.size()[0])
    loss=0
    batch_num=0
    for i in range(0,prepared_grid.size()[0], batch_size):
        indices = permutation[i:i+batch_size]
        if len(indices)<5:
            continue
        # batch= grid[indices]
        
        # batch_grid = grid_prepare(batch)
        batch_grid=prepared_grid[indices]


        batch_types=np.array(list(point_type.values()))[indices.tolist()]
        
        batch_type=dict(zip(batch_grid, batch_types))
        
        batch_dict=grid_sort(batch_type)
        batch_bconds=batch_bconds_transform(batch_grid,bconds)
        batch_bconds = bnd_prepare(batch_bconds, batch_grid,batch_dict, h=h)

        batch_operator = operator_prepare(operator, batch_dict, subset=subset, true_grid=prepared_grid[indices], h=h)
        
        
        loss+= point_sort_shift_loss(model, batch_grid, batch_operator, batch_bconds, lambda_bound=lambda_bound,norm=norm)
        batch_num+=1
    loss=1/batch_num*loss
    return loss


def compute_operator_loss(grid, model, operator, bconds, grid_point_subset=['central'], lambda_bound=10,h=0.001):
    prepared_grid = grid_prepare(grid)
    bconds = bnd_prepare(bconds, prepared_grid, h=h)
    operator = operator_prepare(operator, prepared_grid, subset=grid_point_subset, true_grid=grid, h=h)
    loss = point_sort_shift_loss(model, prepared_grid, operator, bconds, lambda_bound=lambda_bound)
    loss=float(loss.float())
    return loss