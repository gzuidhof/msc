import numpy as np
import logging
import lasagne
import os.path
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import metrics
import util
from logger import initialize_logger
from params import params as P
import pandas as pd
from math import floor

class Trainer(object):

    def __init__(self, metric_names):
        self.model_name = P.MODEL_ID
        self.setup_folders()

        initialize_logger(os.path.join(self.model_folder, 'log.txt').format(self.model_name))
        P.write_to_file(os.path.join(self.model_folder, 'config.ini'))
        logging.info(P.to_string())

        self.train_metrics = metrics.Metrics('train', metric_names, P.N_CLASSES)
        self.val_metrics = metrics.Metrics('validation', metric_names, P.N_CLASSES)
        self.epoch = -1

        self.best_epoch = 0
        self.milestone_epoch = 0
        self.best_accuracy = 0
        self.current_accuracy = 0.
        self.best_train_accuracy = 0.
        self.milestone_tollerance = P.MILESTONE_TOLLERANCE
        self.milestone_inc_factor = P.MILESTONE_INC_FACTOR

    def setup_folders(self):
        self.model_folder = os.path.join('../models',self.model_name)
        self.plot_folder = os.path.join(self.model_folder, 'plots')
        self.image_folder = os.path.join(self.model_folder, 'images')

        folders = ['../models', self.model_folder, self.plot_folder, self.image_folder]
        map(util.make_dir_if_not_present, folders)

    def save_model(self, best=False):
        logging.info("Saving model")

        if best:
            save_filename = os.path.join(self.model_folder,'{}_best_epoch{}.npz'.format(self.model_name, self.epoch))
        else:
            save_filename = os.path.join(self.model_folder,'{}_epoch{}.npz'.format(self.model_name, self.epoch))
        np.savez_compressed(save_filename, *lasagne.layers.get_all_param_values(self.network))

    def plot_and_save_metrics(self):
        labels, train_values_all = self.train_metrics.values_per_epoch()
        labels, val_values_all = self.val_metrics.values_per_epoch()

        for label, train_vals, val_vals in zip(labels, train_values_all, val_values_all):
            plt.figure()
            plt.plot(train_vals)
            plt.plot(val_vals)
            plt.ylabel(label)
            plt.xlabel("Epoch")
            plt.ylim(0,max(1, max(val_vals)*1.5))

            plt.savefig(os.path.join(self.plot_folder, '{}.png'.format(label)))
            plt.close()


        d = {l+"_train": v for l, v in zip(labels, train_values_all)}
        d.update({l+"_val": v for l, v in zip(labels, val_values_all)})

        df = pd.DataFrame(d)
        df.to_csv(os.path.join(self.model_folder,'metrics.csv'))


    def pre_epoch(self):
        self.start_time = time.time()
        self.epoch += 1

    def post_epoch(self):
        logging.info("Epoch {} of {} took {:.3f}s".format(
            self.epoch, P.N_EPOCHS, time.time() - self.start_time))

        labels, train_values = self.train_metrics.batch_done()
        labels, val_values = self.val_metrics.batch_done()
        acc_index = labels.index('Accuracy')
        self.current_accuracy = val_values[acc_index]

        #Print the metrics for this epoch
        for name, train_metric, val_metric in zip(labels, train_values, val_values):
            name = name.rjust(20," ") #Pad the name until 20 characters long
            logging.info("{}:\t {:.6f}\t{:.6f}".format(name,train_metric,val_metric))

        print "train_val, best", train_values[acc_index], self.best_train_accuracy
        print "val_val, best", val_values[acc_index], self.best_accuracy

        print self.milestone_epoch, self.epoch

        if val_values[acc_index] >= self.best_accuracy:
            self.best_accuracy = val_values[acc_index]
            self.milestone_epoch = self.epoch
            self.save_model(best=True)


        #if ((train_values[acc_index] - self.best_train_accuracy) >= P.MILESTONE_ACC_EPSILON or (val_values[acc_index] - self.best_accuracy) >= 0.0):
            #self.best_train_accuracy = train_values[acc_index]
            #self.milestone_epoch = self.epoch
        
        if (self.epoch - self.milestone_epoch) >= self.milestone_tollerance:		
            self.milestone_epoch = self.epoch
            self.milestone_tollerance = self.milestone_tollerance * P.MILESTONE_INC_FACTOR
            self.l_r.set_value(np.float32(self.l_r.get_value()*P.LR_DECAY))
            logging.info("Learning is decreasing to " + str(self.l_r.get_value()))
        else:
            logging.info("Learning rate will be kept at its current value for at least the next {} epochs".format(
            floor(self.milestone_tollerance + self.milestone_epoch - self.epoch)))

        if val_values[acc_index] > self.best_accuracy:
            self.best_accuracy = val_values[acc_index]


        #Make plots for the metrics
        self.plot_and_save_metrics()

        #Save the model (maybe)
        if self.epoch % P.SAVE_EVERY_N_EPOCH == 0:
            self.save_model()


        logging.info("\n")