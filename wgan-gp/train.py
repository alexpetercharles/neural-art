import os
import numpy as np
import tensorflow as tf
import asyncio

from dcgan.models import discriminator, generator
from utils import image

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

# metrics setting
g_loss_metrics = tf.metrics.Mean(name='g_loss')
d_loss_metrics = tf.metrics.Mean(name='d_loss')
total_loss_metrics = tf.metrics.Mean(name='total_loss')

# hyper-parameters
Z_DIM = 100
D_LR = 0.0004
G_LR = 0.0004
RANDOM_SEED = 42
IMAGE_SHAPE = (512, 512, 3)
GP_WEIGHT = 10.0

np.random.seed(RANDOM_SEED)
tf.random.set_seed(RANDOM_SEED)

test_z = tf.random.normal([36, Z_DIM])

def get_random_z(z_dim, batch_size):
    return tf.random.uniform([batch_size, z_dim], minval=-1, maxval=1)

# Wasserstein Loss
def get_loss_fn():
    def d_loss_fn(real_logits, fake_logits):
        return tf.reduce_mean(fake_logits) - tf.reduce_mean(real_logits)

    def g_loss_fn(fake_logits):
        return -tf.reduce_mean(fake_logits)

    return d_loss_fn, g_loss_fn


# Gradient Penalty (GP)
def gradient_penalty(generator, real_images, fake_images, batch_size):
    real_images = tf.cast(real_images, tf.float32)
    fake_images = tf.cast(fake_images, tf.float32)
    alpha = tf.random.uniform([batch_size, 1, 1, 1], 0., 1.)
    diff = fake_images - real_images
    inter = real_images + (alpha * diff)
    with tf.GradientTape() as tape:
        tape.watch(inter)
        predictions = generator(inter)
    gradients = tape.gradient(predictions, [inter])[0]
    slopes = tf.sqrt(tf.reduce_sum(tf.square(gradients), axis=[1, 2, 3]))
    return tf.reduce_mean((slopes - 1.) ** 2)

# generator & discriminator
G = generator.define_model(Z_DIM)
D = discriminator.define_model(IMAGE_SHAPE)

# optimizer
g_optim = tf.keras.optimizers.Adam(G_LR, beta_1=0.5, beta_2=0.999)
d_optim = tf.keras.optimizers.Adam(D_LR, beta_1=0.5, beta_2=0.999)

# loss function
d_loss_fn, g_loss_fn = get_loss_fn()


@tf.function
def train_step(real_images, batch_size):
    z = get_random_z(Z_DIM, batch_size)
    with tf.GradientTape() as d_tape, tf.GradientTape() as g_tape:
        fake_images = G(z, training=True)

        fake_logits = D(fake_images, training=True)
        real_logits = D(real_images, training=True)

        d_loss = d_loss_fn(real_logits, fake_logits)
        g_loss = g_loss_fn(fake_logits)

        gp = gradient_penalty(partial(D, training=True),
                              real_images, fake_images)
        d_loss += gp * GP_WEIGHT

    d_gradients = d_tape.gradient(d_loss, D.trainable_variables)
    g_gradients = g_tape.gradient(g_loss, G.trainable_variables)

    d_optim.apply_gradients(zip(d_gradients, D.trainable_variables))
    g_optim.apply_gradients(zip(g_gradients, G.trainable_variables))

    return g_loss, d_loss


@tf.function
def fake_image_no_train():
    return G(get_random_z(Z_DIM, 1), training=False)

# training loop
def train(ds, batch_size, iteration, log_freq=20):
    ds = iter(ds)
    for step in range(iteration):
        images = next(ds)
        g_loss, d_loss = train_step(images, batch_size)

        g_loss_metrics(g_loss)
        d_loss_metrics(d_loss)
        total_loss_metrics(g_loss + d_loss)

        if step % log_freq == 0:
            template = '[{}/{}] D_loss={:.5f} G_loss={:.5f} Total_loss={:.5f}'
            print(template.format(step, iteration, d_loss_metrics.result(),
                                  g_loss_metrics.result(), total_loss_metrics.result()))
            g_loss_metrics.reset_states()
            d_loss_metrics.reset_states()
            total_loss_metrics.reset_states()
            
            #asyncio.run(image.save_step(fake_image_no_train(), step))
            image.save_step(fake_image_no_train(), step)

        if step % (log_freq * 1000) == 0:
            G.save('./generator')
            D.save('./discriminator')
    
    G.save('./generator')
    D.save('./discriminator')