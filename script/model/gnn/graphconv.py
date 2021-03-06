from math import sqrt
import torch
import torch.nn as nn
import torch.nn.init
from torch.nn import Parameter
import torch.nn.functional as F

import loading.model.model_parameters as param
from utils.tensor import check_for_nan, mean_with_padding

def get_convolution_layer(fmap_in, fmap_out, nb_operators, *args, **kwargs):
  
  conv_type = param.args.conv_type
  conv_args = (fmap_in, fmap_out)
  
  if conv_type == 'ResGNN':
    conv_args += (nb_operators,)
    conv = ResGOpConv
  elif conv_type == 'Simple':
    conv = Simple
  else:
    raise Exception("Convolution type {} not recognized".format(conv_type))

  return conv(*conv_args)

class Simple(nn.Module):
  def __init__(self,fmap_in, fmap_out):
    super(Simple, self).__init__()
    self.fc = nn.Linear(fmap_in, fmap_out)
    self.h_act = nn.ReLU()
    self.emb_act = nn.Tanh()

  def forward(self, ops, emb_in, *args, **kwargs):
    batch,nb_node,fmap= emb_in.size()
    # Embed vertices
    h = self.fc(emb_in)
    h = self.h_act(h)
    # Perform convolution
    A = ops[:,nb_node:,:] # Should be adjacency matrix (will need to improve this)
    emb = self.emb_act(torch.matmul(A, h))
    return emb


def join_operators(adj, operator_iter):
  """Applies each operator in `operator_iter` to adjacency matrix `adj`,
  then change format to be compatible with `GraphOpConv`

  inputs : - adj : adjacency matrix (graph structure).
              shape (batch, n, n) or (batch, edge_fm, n, n)
           - operator_iter : iterable containing graph operators, handeling either
              a single or multiple kernels depending on `adj`

  output : - ops : `GraphOpConv` compatible representation of operators from
              `operator_iter` applied to `adj`.
              shape (batch, n, n * nb_op) or (batch, n, n * edge_fm * nb_op)
  """

  if not operator_iter:  # empty list
      return None
  ops = tuple(operator(adj) for operator in operator_iter)
  ops = torch.cat(ops, 1)

  return ops


class GraphOpConv(nn.Module):
    """Performs graph convolution.
    parameters : - in_fm : number of feature maps in input
                 - out_fm : number of feature maps in output
                 - nb_op : number of graph operators besides identity.abs
                        e.g. x -> a.x * b.Wx has one operator : W

    inputs : - ops : concatenated graph operators, those are being applied
                    to x by right side dot product : x.op
                    shape (batch, nb_node, nb_node * nb_op)
             - emb_in : signal embedding. shape (batch, in_fm, nb_node)

    output : - emb_out : new embedding. shape (batch, out_fm, nb_node)
    """

    def __init__(self, in_fm, out_fm, nb_op):
        super(GraphOpConv, self).__init__()
        self.fc = nn.Linear(in_fm * (nb_op + 1), out_fm)

    def forward(self, ops, emb_in, batch_nb_nodes, adj_mask):
        """Defines the computation performed at every call.
        Computes graph convolution with graph operators `ops`,
        on embedding `emb_in`
        """

        batch_size, nb_node, fmap = emb_in.size()

        # Get mean of features across all nodes
        # Must use batch mean with padding
        '''
        avg = mean_with_padding(
                                emb_in, 
                                batch_nb_nodes, 
                                adj_mask
                                ).unsqueeze(1).expand_as(emb_in)
        '''
        if ops is None:  # permutation invariant kernel
            spread = (emb_in, avg,)
        else:
            spread = torch.bmm(ops, emb_in)
            # Split spreading from different operators 
            # Concatenate on feature maps
            #   (identity operator and average are default)
            spread = spread.split(nb_node, 1)
            # spread = (emb_in, avg,) + spread  
            spread = (emb_in,) + spread  
        spread = torch.cat(spread, 2)

        emb_out = self.fc(spread)

        return emb_out


class ResGOpConv(nn.Module):
  """Residual graph neural network :
          RGC(x) = [ GC(x) || relu(GC(x)) ]
  """

  def __init__(self, in_fm, out_fm, nb_op):
    super(ResGOpConv, self).__init__()

    if out_fm % 2 != 0:
      raise ValueError(
        'ResGOpConv requires even # of output feature maps: {}'.format(out_fm))

    half_out_fm = int(out_fm / 2)
    self.gconv_lin = GraphOpConv(in_fm, half_out_fm, nb_op)
    self.gconv_nlin = GraphOpConv(in_fm, half_out_fm, nb_op)

  def forward(self, ops, emb_in, batch_nb_nodes, adj_mask):
    linear = self.gconv_lin(ops, emb_in, batch_nb_nodes, adj_mask)
    check_for_nan(linear, 'NAN in resgconv : linear')

    nlinear = self.gconv_nlin(ops, emb_in, batch_nb_nodes, adj_mask)
    check_for_nan(nlinear, 'NAN in resgconv : nlinear')
    nlinear = F.relu(nlinear)

    emb_out = torch.cat((linear, nlinear), 2)

    if (emb_out != emb_out).data.sum() > 0:
      print('NAN in first gconv : before return')
      assert False

    return emb_out
