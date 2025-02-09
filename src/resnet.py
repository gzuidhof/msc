import sys
sys.setrecursionlimit(10000)
import lasagne
from lasagne.nonlinearities import rectify, softmax, sigmoid
from lasagne.layers import InputLayer, MaxPool2DLayer, DenseLayer, DropoutLayer, helper, batch_norm, BatchNormLayer
# for ResNet
from lasagne.layers.dnn import Conv2DDNNLayer as ConvLayer
from lasagne.layers import Pool2DLayer, ElemwiseSumLayer, NonlinearityLayer, PadLayer, GlobalPoolLayer, ExpressionLayer
from lasagne.init import Orthogonal, HeNormal, GlorotNormal
from lasagne.updates import nesterov_momentum, adam

import theano
import theano.tensor as T
import numpy as np
from params import params as P

PIXELS = P.INPUT_SIZE
image_size = PIXELS * PIXELS
num_classes = P.N_CLASSES
n_channels = P.CHANNELS
dropout_ratio = P.DROPOUT

he_norm = HeNormal(gain='relu')

def ResNet_Stacked(output_of_network, n=4, k=2):

    def residual_block(l, increase_dim=False, projection=True, first=False, filters=16):
        if increase_dim:
            first_stride = (2,2)
        else:
            first_stride = (1,1)

        if first:
            # hacky solution to keep layers correct
            bn_pre_relu = l
        else:
            # contains the BN -> ReLU portion, steps 1 to 2
            bn_pre_conv = BatchNormLayer(l)
            bn_pre_relu = NonlinearityLayer(bn_pre_conv, rectify)

        # contains the weight -> BN -> ReLU portion, steps 3 to 5
        conv_1 = batch_norm(ConvLayer(bn_pre_relu, num_filters=filters, filter_size=(3,3), stride=first_stride, nonlinearity=rectify, pad='same', W=he_norm))

        if not np.isclose(dropout_ratio, 0.0):
			conv_1 = DropoutLayer(conv_1, p=dropout_ratio)

        # contains the last weight portion, step 6
        conv_2 = ConvLayer(conv_1, num_filters=filters, filter_size=(3,3), stride=(1,1), nonlinearity=None, pad='same', W=he_norm)

        # add shortcut connections
        if increase_dim:
            # projection shortcut, as option B in paper
            projection = ConvLayer(l, num_filters=filters, filter_size=(1,1), stride=(2,2), nonlinearity=None, pad='same', b=None)
            block = ElemwiseSumLayer([conv_2, projection])

        elif first:
            # projection shortcut, as option B in paper
            projection = ConvLayer(l, num_filters=filters, filter_size=(1,1), stride=(1,1), nonlinearity=None, pad='same', b=None)
            block = ElemwiseSumLayer([conv_2, projection])
        else:
            block = ElemwiseSumLayer([conv_2, l])

        return block



    l = output_of_network
    l = MaxPool2DLayer(l, 2)
    l = batch_norm(ConvLayer(l, num_filters = 64*k, filter_size=(3,3), stride=(1,1), nonlinearity=rectify, W=HeNormal(gain='relu'), pad='same'))
    
    l = residual_block(l, first=True, increase_dim=True, filters=k*64)
    for _ in range(1,(n+2)):
        l = residual_block(l, filters=k*64)
    
    bn_post_conv = BatchNormLayer(l)
    l = bn_post_relu = NonlinearityLayer(bn_post_conv, rectify)

    l = MaxPool2DLayer(l, 2)
    l = batch_norm(ConvLayer(l, num_filters = 192, filter_size=(3,3), stride=(1,1), nonlinearity=rectify, W=HeNormal(gain='relu'), pad='same'))
    l = batch_norm(ConvLayer(l, num_filters = 192, filter_size=(3,3), stride=(1,1), nonlinearity=rectify, W=HeNormal(gain='relu'), pad='same'))
    
    
    
    l = MaxPool2DLayer(l, 2)
    remaining_size = l.output_shape[2]
    print l.output_shape

    l = batch_norm(ConvLayer(l, num_filters=256, filter_size=(remaining_size,remaining_size), nonlinearity=rectify, W=HeNormal(gain='relu')))
    l = ConvLayer(l, num_filters=3, filter_size=(1,1), nonlinearity=rectify, W=HeNormal(gain='relu'))
    l = GlobalPoolLayer(l)
    # fully connected layer
    network = DenseLayer(l, num_units=num_classes, W=HeNormal(), nonlinearity=softmax)

    return network

def ResNet_Stacked_Old(output_of_network):
    l = output_of_network

    l = batch_norm(ConvLayer(l, num_filters=256, filter_size=(3,3), nonlinearity=rectify, W=HeNormal()))
    l = MaxPool2DLayer(l,pool_size=2)
    l = batch_norm(ConvLayer(l, num_filters=256, filter_size=(3,3), nonlinearity=rectify, W=HeNormal()))

    l = GlobalPoolLayer(l)

    l = DenseLayer(l, num_units=num_classes, W=HeNormal(), nonlinearity=softmax)

    return l


def ResNet_FullPre_Wide(input_var=None, n=6, k=4):
    '''
    Adapted from https://github.com/Lasagne/Recipes/tree/master/papers/deep_residual_learning.

    Tweaked to be consistent with 'Identity Mappings in Deep Residual Networks', Kaiming He et al. 2016 (https://arxiv.org/abs/1603.05027)

    And 'Wide Residual Networks', Sergey Zagoruyko, Nikos Komodakis 2016 (http://arxiv.org/pdf/1605.07146v1.pdf)

    Depth = 6n + 2
    '''
    n_filters = {0:16, 1:16*k, 2:32*k, 3:64*k, 4:96*k}

    # create a residual learning building block with two stacked 3x3 convlayers as in paper
    def residual_block(l, increase_dim=False, projection=True, first=False, filters=16):
        if increase_dim:
            first_stride = (2,2)
        else:
            first_stride = (1,1)

        if first:
            # hacky solution to keep layers correct
            bn_pre_relu = l
        else:
            # contains the BN -> ReLU portion, steps 1 to 2
            bn_pre_conv = BatchNormLayer(l)
            bn_pre_relu = NonlinearityLayer(bn_pre_conv, rectify)

        # contains the weight -> BN -> ReLU portion, steps 3 to 5
        conv_1 = batch_norm(ConvLayer(bn_pre_relu, num_filters=filters, filter_size=(3,3), stride=first_stride, nonlinearity=rectify, pad='same', W=he_norm))

        if not np.isclose(dropout_ratio, 0.0):
			conv_1 = DropoutLayer(conv_1, p=dropout_ratio)

        # contains the last weight portion, step 6
        conv_2 = ConvLayer(conv_1, num_filters=filters, filter_size=(3,3), stride=(1,1), nonlinearity=None, pad='same', W=he_norm)

        # add shortcut connections
        if increase_dim:
            # projection shortcut, as option B in paper
            projection = ConvLayer(l, num_filters=filters, filter_size=(1,1), stride=(2,2), nonlinearity=None, pad='same', b=None)
            block = ElemwiseSumLayer([conv_2, projection])

        elif first:
            # projection shortcut, as option B in paper
            projection = ConvLayer(l, num_filters=filters, filter_size=(1,1), stride=(1,1), nonlinearity=None, pad='same', b=None)
            block = ElemwiseSumLayer([conv_2, projection])
        else:
            block = ElemwiseSumLayer([conv_2, l])

        return block

    # Building the network
    l_in = InputLayer(shape=(None, P.CHANNELS, PIXELS, PIXELS), input_var=input_var)

    #print "IMAGE SIZE", image_size

    # first layer, output is 16 x 64 x 64
    l = batch_norm(ConvLayer(l_in, num_filters=n_filters[0], filter_size=(3,3), stride=(1,1), nonlinearity=rectify, pad='same', W=he_norm))

    # first stack of residual blocks, output is 32 x 64 x 64
    l = residual_block(l, first=True, filters=n_filters[1])
    for _ in range(1,n):
        l = residual_block(l, filters=n_filters[1])

    # second stack of residual blocks, output is 64 x 32 x 32
    l = residual_block(l, increase_dim=True, filters=n_filters[2])
    for _ in range(1,(n+2)):
        l = residual_block(l, filters=n_filters[2])

    # third stack of residual blocks, output is 128 x 16 x 16
    l = residual_block(l, increase_dim=True, filters=n_filters[3])
    for _ in range(1,(n+2)):
        l = residual_block(l, filters=n_filters[3])

    bn_post_conv = BatchNormLayer(l)
    bn_post_relu = NonlinearityLayer(bn_post_conv, rectify)

    # average pooling
    avg_pool = GlobalPoolLayer(bn_post_relu)

    # fully connected layer
    network = DenseLayer(avg_pool, num_units=num_classes, W=HeNormal(), nonlinearity=softmax)

    return network


def define_updates(output_layer, X, Y):
    output_train = lasagne.layers.get_output(output_layer)
    output_test = lasagne.layers.get_output(output_layer, deterministic=True)

    # set up the loss that we aim to minimize when using cat cross entropy our Y should be ints not one-hot
    loss = lasagne.objectives.categorical_crossentropy(T.clip(output_train,0.000001,0.999999), Y)
    loss = loss.mean()

    acc = T.mean(T.eq(T.argmax(output_train, axis=1), Y), dtype=theano.config.floatX)

    # if using ResNet use L2 regularization
    all_layers = lasagne.layers.get_all_layers(output_layer)
    l2_penalty = lasagne.regularization.regularize_layer_params(all_layers, lasagne.regularization.l2) * P.L2_LAMBDA
    loss = loss + l2_penalty

    # set up loss functions for validation dataset
    test_loss = lasagne.objectives.categorical_crossentropy(T.clip(output_test,0.000001,0.999999), Y)
    test_loss = test_loss.mean()
    test_loss = test_loss + l2_penalty

    test_acc = T.mean(T.eq(T.argmax(output_test, axis=1), Y), dtype=theano.config.floatX)

    # get parameters from network and set up sgd with nesterov momentum to update parameters, l_r is shared var so it can be changed
    l_r = theano.shared(np.array(P.LEARNING_RATE, dtype=theano.config.floatX))
    params = lasagne.layers.get_all_params(output_layer, trainable=True)
    updates = nesterov_momentum(loss, params, learning_rate=l_r, momentum=P.MOMENTUM)
    #updates = adam(loss, params, learning_rate=l_r)

    prediction_binary = T.argmax(output_train, axis=1)
    test_prediction_binary = T.argmax(output_test, axis=1)

    # set up training and prediction functions
    train_fn = theano.function(inputs=[X,Y], outputs=[loss, l2_penalty, acc, prediction_binary, output_train[:,1]], updates=updates)
    valid_fn = theano.function(inputs=[X,Y], outputs=[test_loss, l2_penalty, test_acc, test_prediction_binary, output_test[:,1]])

    return train_fn, valid_fn, l_r

def define_predict(output_layer, X):
    output = lasagne.layers.get_output(output_layer, deterministic=True)
    #loss = lasagne.objectives.categorical_crossentropy(output, Y)
    #acc = T.mean(T.eq(T.argmax(output, axis=1), Y), dtype=theano.config.floatX)
    prediction_binary = T.argmax(output, axis=1)

    prediction_fn = theano.function(inputs=[X], outputs=[prediction_binary, output])
    return prediction_fn





