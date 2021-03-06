import torch
import torch.nn as nn
from torch.autograd import Variable

from model.kernels.build_kernels import get_kernels
from model.kernels.build_combine_kernels import get_combine_kernels
from model.gnn.build_layers import get_layers
from model.readout.readout import get_readout

class GNN(nn.Module):
  '''
  Graph neural network:
    - Runs through several graph convolution layers of specified type
    - Performs final classification using logistic regression
  '''
  def __init__(self):
    super(GNN, self).__init__()
    self.layers = get_layers(
                             kernels = get_kernels(),
                             combine_kernels = get_combine_kernels()
                             )
    self.readout = get_readout()

  def forward(self, emb, mask, batch_nb_nodes, plotting=None):
    batch_size, nb_pts, fmap  = emb.size()

    # Create dummy first adjacency matrix
    adj = Variable(torch.ones(batch_size, nb_pts, nb_pts))
    if emb.is_cuda:
      adj = adj.cuda()

    # Run through layers
    for i, layer in enumerate(self.layers):
      emb, adj = layer(emb, adj, mask, batch_nb_nodes)
      # Apply any plotting
      if plotting is not None:
        plotting.plot_graph(emb[0].data.cpu().numpy(),adj[0].data.cpu().numpy(),i)

    # Apply final readout and return
    return self.readout(emb, mask, batch_nb_nodes)
