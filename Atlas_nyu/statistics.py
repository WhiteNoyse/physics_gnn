from os.path import join
from utils.files import makefile_if_not_there, print_
from math import sqrt


class Statistics:
    """Object to store, update, print the statistics from one model"""

    def __init__(self, param, nbnetparam, parameters_used, stdout=None):
        self.param = param
        self.stdout = stdout

        # initiate description
        self.description = makedescription(param, nbnetparam)
        makefile_if_not_there(self.param.netdir, 'description.txt',
                              text=self.description)

        # initiate buffers
        self.stats = ['loss', 'kernel', 'avg0', 'avg1', 'std0', 'std1']
        self.nb_batch_in_buffer = {'train': 0, 'test': 0}
        self.buffer = {'train': dict(), 'test': dict()}
        self._init_buffer('train')
        self._init_buffer('test')
        self.steploss = 0.0
        self.steps = 0

        # initiate files
        self._init_files()

        # initiate train counter
        self.nb_events_seen = {'train': 0, 'test': 0}

    def newparameters(self, param, nbnetparam, stdout=None):
        self.param = param
        self.stdout = stdout
        self.description = makedescription(param, nbnetparam)

    def update(self, mode, output, labels, loss_step, kernel_std):
        self.nb_events_seen[mode] += labels.numel()

        # update step loss
        if mode == 'train':
            self.steploss += loss_step
            self.steps += 1
            if self.steps >= self.param.nbstep:
                self.write_stat('loss_step', loss_step / self.param.nbstep)
                self.steploss = 0.0
                self.steps = 0

        nb_ones = labels.sum()
        output_ones = output * labels
        output_avg_ones = output_ones.sum()
        output_sqr_ones = (output_ones ** 2).sum()

        nb_zero = (1 - labels).sum()
        output_zero = output * (1 - labels)
        output_avg_zero = output_zero.sum()
        output_sqr_zero = (output_zero ** 2).sum()

        # update buffers for average stats
        self.buffer[mode]['loss'] += loss_step
        self.buffer[mode]['kernel'] += kernel_std

        self.buffer[mode]['nb_ones'] += nb_ones
        self.buffer[mode]['avg1'] += output_avg_ones
        self.buffer[mode]['std1'] += output_sqr_ones

        self.buffer[mode]['nb_zero'] += nb_zero
        self.buffer[mode]['avg0'] += output_avg_zero
        self.buffer[mode]['std0'] += output_sqr_zero

        self._update_buffer(mode)

    def _update_buffer(self, mode):
        # update counter, write in files if enough batches in buffer
        self.nb_batch_in_buffer[mode] += 1
        if self.nb_batch_in_buffer[mode] >= self.param.nbdisplay:
            self.buffer[mode]['loss'] /= self.param.nbdisplay
            self.buffer[mode]['kernel'] /= self.param.nbdisplay

            if self.buffer[mode]['nb_ones'] > 0:
                self.buffer[mode]['avg1'] /= self.buffer[mode]['nb_ones']
                var1 = self.buffer[mode]['std1'] / self.buffer[mode]['nb_ones']
                var1 -= self.buffer[mode]['avg1'] ** 2
                var1 = max(0, var1)  # prevents negative variance from approximation
                self.buffer[mode]['std1'] = sqrt(var1)

            if self.buffer[mode]['nb_zero'] > 0:
                self.buffer[mode]['avg0'] /= self.buffer[mode]['nb_zero']
                var0 = self.buffer[mode]['std0'] / self.buffer[mode]['nb_zero']
                var0 -= self.buffer[mode]['avg0'] ** 2
                var0 = max(0, var0)  # prevents negative variance from approximation
                self.buffer[mode]['std0'] = sqrt(var0)

            if mode == 'train':
                for stat in self.stats:
                    self.write_stat(stat, self.buffer[mode][stat])

                # print average stats
                print_(
                    '{: >10} events : '.format(self.nb_events_seen[mode]) +
                    ' - '.join(
                        '{}: {:.2E}'.format(stat, self.buffer[mode][stat])
                        for stat in self.stats),
                    stdout=self.stdout)

            else:
                print_(
                    '{: >10} events : '.format(self.nb_events_seen[mode]) +
                    ' - '.join(
                        '{}: {:.2E}'.format(stat, self.buffer[mode][stat])
                        for stat in self.stats if 'loss' not in stat))

            # Restart buffers
            self._init_buffer(mode)

    def _init_files(self):
        makefile_if_not_there(self.param.statdir, 'loss_step.csv')
        for stat in self.stats:
            makefile_if_not_there(self.param.statdir, '{}.csv'.format(stat))

    def _init_buffer(self, mode):
        self.nb_batch_in_buffer[mode] = 0
        for stat in self.stats:
            self.buffer[mode][stat] = 0
        self.buffer[mode]['nb_ones'] = 0
        self.buffer[mode]['nb_zero'] = 0

    def write_stat(self, statname, value):
        filename = '{}.csv'.format(statname)
        with open(join(self.param.statdir, filename), 'a') as fout:
            fout.write('{},'.format(value))

    def flush(self):
        # flush test stat files and buffers
        self.steploss = 0.0
        for stat in self.stats:
            self.buffer['test'][stat] = 0

        # flush test counter
        self.nb_events_seen['test'] = 0

    def printdescr(self):
        """prints description"""

        descr = self.description + \
            'Trained on {} examples.\n'.format(self.nb_events_seen['train']) + \
            '{}ing using {}.\n'.format(
                self.param.mode, 'GPU' if self.param.cuda else 'CPU')

        print_(descr, self.stdout)


def makedescription(param, nbnetparam):
    descr = '{} :\n'.format(param.model) + '-' * 20 + '\n'
    descr = descr + '\n'.join('{}: {}'.format(parameter, param.__dict__[parameter]) for parameter in param.__dict__.keys())

    descr = descr + '\n' + '-' * 20 + \
        '\nTotal of {} parameters\n\n'.format(nbnetparam)

    return descr
