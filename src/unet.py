import theano
import theano.tensor as T
import lasagne
from lasagne.layers import InputLayer, Conv2DLayer, MaxPool2DLayer
from lasagne.init import HeNormal
from lasagne import nonlinearities
from lasagne.layers import ConcatLayer, Upscale2DLayer
from lasagne.regularization import l2, regularize_network_params

def output_size_for_input(in_size, depth):
    in_size -= 4
    for _ in range(depth-1):
        in_size = in_size//2
        in_size -= 4
    for _ in range(depth-1):
        in_size = in_size*2
        in_size -= 4
    return in_size

NET_DEPTH = 5
INPUT_SIZE = 572
#INPUT_SIZE = 572
OUTPUT_SIZE = output_size_for_input(INPUT_SIZE, NET_DEPTH)

def filter_for_depth(depth):
    return 2**(5+depth)

def define_network(input_var):
    num_classes = 3

    batch_size = None
    net = {}
    net['input'] = InputLayer(shape=(batch_size,num_classes,INPUT_SIZE,INPUT_SIZE), input_var=input_var)

    nonlinearity = nonlinearities.rectify

    def contraction(depth, deepest):
        n_filters = filter_for_depth(depth)
        incoming = net['input'] if depth == 0 else net['pool{}'.format(depth-1)]

        net['conv{}_1'.format(depth)] = Conv2DLayer(incoming,
                                    num_filters=n_filters, filter_size=3, pad='valid',
                                    W=HeNormal(gain='relu'),
                                    nonlinearity=nonlinearity)
        net['conv{}_2'.format(depth)] = Conv2DLayer(net['conv{}_1'.format(depth)],
                                    num_filters=n_filters, filter_size=3, pad='valid',
                                    W=HeNormal(gain='relu'),
                                    nonlinearity=nonlinearity)

        if not deepest:
            net['pool{}'.format(depth)] = MaxPool2DLayer(net['conv{}_2'.format(depth)], pool_size=2, stride=2)

    def expansion(depth, deepest):
        n_filters = filter_for_depth(depth)

        incoming = net['conv{}_2'.format(depth+1)] if deepest else net['_conv{}_2'.format(depth+1)]

        upscaling = Upscale2DLayer(incoming,4)
        net['upconv{}'.format(depth)] = Conv2DLayer(upscaling,
                                        num_filters=n_filters, filter_size=2, stride=2,
                                        W=HeNormal(gain='relu'),
                                        nonlinearity=nonlinearity)

        net['bridge{}'.format(depth)] = ConcatLayer([
                                        net['upconv{}'.format(depth)],
                                        net['conv{}_2'.format(depth)]],
                                        axis=1, cropping=[None, None, 'center', 'center'])

        net['_conv{}_1'.format(depth)] = Conv2DLayer(net['bridge{}'.format(depth)],
                                        num_filters=n_filters, filter_size=3, pad='valid',
                                        W=HeNormal(gain='relu'),
                                        nonlinearity=nonlinearity)
        net['_conv{}_2'.format(depth)] = Conv2DLayer(net['_conv{}_1'.format(depth)],
                                        num_filters=n_filters, filter_size=3, pad='valid',
                                        W=HeNormal(gain='relu'),
                                        nonlinearity=nonlinearity)

    for d in range(NET_DEPTH):
        #There is no pooling at the last layer
        deepest = d == NET_DEPTH-1
        contraction(d, deepest)

    for d in reversed(range(NET_DEPTH-1)):
        deepest = d == NET_DEPTH-2
        expansion(d, deepest)

    # Output layer
    net['out'] = Conv2DLayer(net['_conv0_2'], num_filters=num_classes, filter_size=(1,1), pad='valid',
                                    nonlinearity=None)

    #import network_repr
    #print network_repr.get_network_str(net['out'])
    print 'Network output shape', lasagne.layers.get_output_shape(net['out'])
    return net

def score_metrics(out, target_var, weight_map, l2_loss=0):
    _EPSILON=1e-8

    out_flat = out.dimshuffle(1,0,2,3).flatten(ndim=2).dimshuffle(1,0)
    target_flat = target_var.dimshuffle(1,0,2,3).flatten(ndim=1)
    weight_flat = weight_map.dimshuffle(1,0,2,3).flatten(ndim=1)

    prediction = lasagne.nonlinearities.softmax(out_flat)
    prediction_binary = T.argmax(prediction, axis=1)

    dice_score = (T.sum(T.eq(2, prediction_binary+target_flat))*2.0 /
                    (T.sum(prediction_binary) + T.sum(target_flat)))

    loss = lasagne.objectives.categorical_crossentropy(T.clip(prediction,_EPSILON,1-_EPSILON), target_flat)
    loss = loss * weight_flat
    loss = loss.mean()
    loss += l2_loss

    accuracy = T.mean(T.eq(prediction_binary, target_flat),
                      dtype=theano.config.floatX)

    return loss, accuracy, dice_score, target_flat, prediction, prediction_binary


def define_updates(network, input_var, target_var, weight_var):
    l2_lambda = 2e-5 #Weight decay
    learning_rate = learning_rate=0.00002
    momentum = 0.99

    params = lasagne.layers.get_all_params(network, trainable=True)

    out = lasagne.layers.get_output(network)
    test_out = lasagne.layers.get_output(network, deterministic=True)

    l2_loss = l2_lambda * regularize_network_params(network, l2)

    train_metrics = score_metrics(out, target_var, weight_var, l2_loss)
    loss, acc, dice_score, target_prediction, prediction, prediction_binary = train_metrics

    val_metrics = score_metrics(test_out, target_var, weight_var, l2_loss)
    t_loss, t_acc, t_dice_score, t_target_prediction, t_prediction, t_prediction_binary = train_metrics

    updates = lasagne.updates.nesterov_momentum(
            loss, params, learning_rate=learning_rate, momentum=momentum)

    print "Defining train function"
    train_fn = theano.function([input_var, target_var, weight_var],[
                                loss, l2_loss, acc, dice_score, target_prediction, prediction, prediction_binary],
                                updates=updates)

    print "Defining validation function"
    val_fn = theano.function([input_var, target_var, weight_var], [
                                t_loss, l2_loss, t_acc, t_dice_score, t_target_prediction, t_prediction, t_prediction_binary])


    return train_fn, val_fn
