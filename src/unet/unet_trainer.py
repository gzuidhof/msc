from __future__ import division
import time
import numpy as np
import trainer
from params import params as P
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from functools import partial
import patch_sampling
import logging
import scipy.misc
from parallel import ParallelBatchIterator
from tqdm import tqdm
import os.path

if __name__ == "__main__":
    import theano
    import theano.tensor as T
    import lasagne
    import unet
    from unet import INPUT_SIZE, OUTPUT_SIZE

class UNetTrainer(trainer.Trainer):
    def __init__(self):
        metric_names = ['Loss','L2','Accuracy','Dice']
        super(UNetTrainer, self).__init__(metric_names)

        input_var = T.tensor4('inputs')
        target_var = T.tensor4('targets', dtype='int64')
        weight_var = T.tensor4('weights')


        logging.info("Defining network")
        net_dict = unet.define_network(input_var)
        self.network = net_dict['out']
        train_fn, val_fn = unet.define_updates(self.network, input_var, target_var, weight_var)

        self.train_fn = train_fn
        self.val_fn = val_fn

    def do_batches(self, fn, batch_generator, metrics):
        for i, batch in enumerate(tqdm(batch_generator)):
            inputs, targets, weights, _ = batch

            err, l2_loss, acc, dice, true, prob, prob_b = fn(inputs, targets, weights)

            metrics.append([err, l2_loss, acc, dice])
            metrics.append_prediction(true, prob_b)

            if i % 10 == 0:
                im = np.hstack((
                     true[:OUTPUT_SIZE**2].reshape(OUTPUT_SIZE,OUTPUT_SIZE),
                     prob[:OUTPUT_SIZE**2][:,1].reshape(OUTPUT_SIZE,OUTPUT_SIZE)))
                plt.imsave(os.path.join(self.image_folder,'{0}_epoch{1}.png'.format(metrics.name, self.epoch)),im)


    def train(self):
        filenames_train, filenames_val = patch_sampling.get_filenames()
        generator = partial(patch_sampling.extract_random_patches, patch_size=P.INPUT_SIZE, crop_size=OUTPUT_SIZE)

        logging.info("Starting training...")

        for epoch in range(P.N_EPOCHS):
            self.pre_epoch()

            #Full pass over the training data
            np.random.shuffle(filenames_train)
            train_gen = ParallelBatchIterator(generator, filenames_train, ordered=False,
                                                batch_size=P.BATCH_SIZE_TRAIN,
                                                multiprocess=P.MULTIPROCESS_LOAD_AUGMENTATION,
                                                n_producers=P.N_WORKERS_LOAD_AUGMENTATION)

            self.do_batches(self.train_fn, train_gen, self.train_metrics)

            # And a full pass over the validation data:
            val_gen = ParallelBatchIterator(generator, filenames_val, ordered=False,
                                                batch_size=P.BATCH_SIZE_VALIDATION,
                                                multiprocess=P.MULTIPROCESS_LOAD_AUGMENTATION,
                                                n_producers=P.N_WORKERS_LOAD_AUGMENTATION)

            self.do_batches(self.val_fn, val_gen, self.val_metrics)
            self.post_epoch()



if __name__ == "__main__":
    trainer = UNetTrainer()
    trainer.train()