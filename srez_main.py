import srez_demo
import srez_input
import srez_model
import srez_train

import os.path
import random
import numpy as np
import numpy.random

import tensorflow as tf

FLAGS = tf.app.flags.FLAGS

# Configuration (alphabetically)
tf.app.flags.DEFINE_integer('batch_size', 16,
                            "Number of samples per batch.")

tf.app.flags.DEFINE_string('checkpoint_dir', 'checkpoint',
                           "Output folder where checkpoints are dumped.")

tf.app.flags.DEFINE_integer('checkpoint_period', 10000,
                            "Number of batches in between checkpoints")

tf.app.flags.DEFINE_string('summary_dir', 'summary',
                            "Diretory to save TensorBoard summaries")

tf.app.flags.DEFINE_string('dataset', 'dataset',
                           "Path to the dataset directory.")

tf.app.flags.DEFINE_float('epsilon', 1e-8,
                          "Fuzz term to avoid numerical instability")

tf.app.flags.DEFINE_string('run', 'demo',
                            "Which operation to run. [demo|train]")

tf.app.flags.DEFINE_float('gene_l1_factor', .90,
                          "Multiplier for generator L1 loss term")

tf.app.flags.DEFINE_float('learning_beta1', 0.5,
                          "Beta1 parameter used for AdamOptimizer")

tf.app.flags.DEFINE_float('learning_beta2', 0.9,
                          "Beta1 parameter used for AdamOptimizer")

tf.app.flags.DEFINE_float('learning_rate_start', 0.00010,
                          "Starting learning rate used for AdamOptimizer")

tf.app.flags.DEFINE_float('train_noise', 0.03,
                          "level of Gaussian noise added to training images")

tf.app.flags.DEFINE_integer('learning_rate_half_life', 5000,
                            "Number of batches until learning rate is halved")

tf.app.flags.DEFINE_bool('log_device_placement', False,
                         "Log the device where variables are placed.")

tf.app.flags.DEFINE_integer('sample_size', 64,
                            "Image sample size in pixels. Range [64,128]")

tf.app.flags.DEFINE_integer('summary_period', 200,
                            "Number of batches between summary data dumps")

tf.app.flags.DEFINE_integer('random_seed', 0,
                            "Seed used to initialize rng.")

tf.app.flags.DEFINE_integer('test_vectors', 16,
                            """Number of features to use for testing""")
                            
tf.app.flags.DEFINE_string('train_dir', 'train',
                           "Output folder where training logs are dumped.")

tf.app.flags.DEFINE_integer('train_time', 200,
                            "Time in minutes to train the model")

tf.app.flags.DEFINE_integer('optimizer', 0,
                            "Which optimizer to use: RMSprop(1) or Adam (0)?")

tf.app.flags.DEFINE_integer('loss_func', 0,
                            "Which loss function to use: DCGAN(1) or WGAN (0)?")

tf.app.flags.DEFINE_integer('weigh_clip', 0,
                            "Perform weigh clipping(1) or not(0)?")

tf.app.flags.DEFINE_integer('batch_norm', 0,
                            "Perform batch normalization in the discriminator (1) or not(0)?")

tf.app.flags.DEFINE_integer('output_image', 1,
                            "Present images from all methods (0) or only present images from the generator (1)")

tf.app.flags.DEFINE_integer('LAMBDA', 2,
                            "Gradient penalty lambda hyperparameter in improved WGAN")

def prepare_dirs(delete_train_dir=False):
    # Create checkpoint dir (do not delete anything)
    if not tf.gfile.Exists(FLAGS.checkpoint_dir):
        tf.gfile.MakeDirs(FLAGS.checkpoint_dir)

    # Create summary dir
    if not tf.gfile.Exists(FLAGS.summary_dir):
        tf.gfile.MakeDirs(FLAGS.summary_dir)
        
    # Cleanup train dir
    if delete_train_dir:
        if tf.gfile.Exists(FLAGS.train_dir):
            tf.gfile.DeleteRecursively(FLAGS.train_dir)
        tf.gfile.MakeDirs(FLAGS.train_dir)

    # Return names of training files
    if not tf.gfile.Exists(FLAGS.dataset) or \
       not tf.gfile.IsDirectory(FLAGS.dataset):
        raise FileNotFoundError("Could not find folder `%s'" % (FLAGS.dataset,))

    filenames = tf.gfile.ListDirectory(FLAGS.dataset)
    filenames = sorted(filenames)
    random.shuffle(filenames)
    filenames = [os.path.join(FLAGS.dataset, f) for f in filenames]

    return filenames


def setup_tensorflow():
    # Create session
    config = tf.ConfigProto(log_device_placement=FLAGS.log_device_placement)
    sess = tf.Session(config=config)

    # Initialize rng with a deterministic seed
    with sess.graph.as_default():
        tf.set_random_seed(FLAGS.random_seed)
        
    random.seed(FLAGS.random_seed)
    np.random.seed(FLAGS.random_seed)

    summary_writer = tf.summary.FileWriter(FLAGS.summary_dir, sess.graph)

    return sess, summary_writer

def _demo():
    # Load checkpoint
    if not tf.gfile.IsDirectory(FLAGS.checkpoint_dir):
        raise FileNotFoundError("Could not find folder `%s'" % (FLAGS.checkpoint_dir,))

    # Setup global tensorflow state
    sess, summary_writer = setup_tensorflow()

    # Prepare directories
    filenames = prepare_dirs(delete_train_dir=False)

    # Setup async input queues
    features, labels = srez_input.setup_inputs(sess, filenames)

    # Create and initialize model
    [gene_minput, gene_moutput,
     gene_output, gene_var_list,
     disc_real_output, disc_fake_output, disc_var_list] = \
            srez_model.create_model(sess, features, labels)

    # Restore variables from checkpoint
    saver = tf.train.Saver()
    filename = 'checkpoint_new.txt'
    filename = os.path.join(FLAGS.checkpoint_dir, filename)
    saver.restore(sess, filename)

    # Execute demo
    srez_demo.demo1(sess)

class TrainData(object):
    def __init__(self, dictionary):
        self.__dict__.update(dictionary)

def _train():
    # Setup global tensorflow state
    sess, summary_writer = setup_tensorflow()

    # Prepare directories
    all_filenames = prepare_dirs(delete_train_dir=True)

    # Separate training and test sets
    train_filenames = all_filenames[:-FLAGS.test_vectors]
    test_filenames  = all_filenames[-FLAGS.test_vectors:]

    # TBD: Maybe download dataset here

    # Setup async input queues
    train_features, train_labels = srez_input.setup_inputs(sess, train_filenames)
    test_features,  test_labels  = srez_input.setup_inputs(sess, test_filenames)

    # Add some noise during training (think denoising autoencoders)
    noise_level = FLAGS.train_noise
    noisy_train_features = train_features + \
                           tf.random_normal(train_features.get_shape(), stddev=noise_level)

    [gene_minput, gene_moutput,gene_output, gene_var_list,
     disc_real_output, disc_fake_output, gradients, disc_var_list] = \
            srez_model.create_model(sess, noisy_train_features, train_labels)


    gene_loss = srez_model.create_generator_loss(disc_fake_output, gene_output, train_features)
    disc_real_loss, disc_fake_loss = \
                     srez_model.create_discriminator_loss(disc_real_output, disc_fake_output)

    if FLAGS.loss_func:
        # for DCGAN
        disc_loss = tf.add(disc_real_loss, disc_fake_loss, name='disc_loss')
    else:
        # for WGAN
        disc_loss = tf.subtract(disc_real_loss, disc_fake_loss, name='disc_loss')
    
    if FLAGS.LAMBDA > 0:
        slopes = tf.sqrt(tf.reduce_sum(tf.square(gradients), reduction_indices=[1]))
        gradient_penalty = tf.reduce_mean((slopes-1.)**2)
        disc_loss = tf.add(disc_loss, FLAGS.LAMBDA*gradient_penalty, name='disc_loss')

    (global_step, learning_rate, gene_minimize, disc_minimize, d_clip) = \
            srez_model.create_optimizers(gene_loss, gene_var_list, disc_loss, disc_var_list)

    tf.summary.scalar('generator_loss', gene_loss)
    tf.summary.scalar('discriminator_real_loss', disc_real_loss)
    tf.summary.scalar('discriminator_fake_loss', disc_fake_loss)
    tf.summary.scalar('discriminator_tot_loss', disc_loss)


    # Train model
    train_data = TrainData(locals())
    srez_train.train_model(train_data)

def main(argv=None):
    # Training or showing off?

    if FLAGS.run == 'demo':
        _demo()
    elif FLAGS.run == 'train':
        _train()

if __name__ == '__main__':
  tf.app.run()
