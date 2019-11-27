import os

import numpy as np
import tensorflow as tf
from datasets.data_generator import *
from datasets import my_dataset
from mrcnn import mask_rcnn
from config import *

os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
print(tf.__version__)
assert tf.__version__.startswith('2.')
tf.random.set_seed(2019)
np.random.seed(2019)

img_mean = (123.675, 116.28, 103.53)
# img_std = (58.395, 57.12, 57.375)
img_std = (1., 1., 1.)

batch_size = 2
num_classes = 2


class BalloonConfig(Config):
    """Configuration for training on the toy  dataset.
    Derives from the base Config class and overrides some values.
    """
    # Give the configuration a recognizable name
    NAME = "balloon"

    # We use a GPU with 12GB memory, which can fit two data.
    # Adjust down if you use a smaller GPU.
    IMAGES_PER_GPU = 2

    # Number of classes (including background)
    NUM_CLASSES = 1 + 1  # Background + balloon

    # Number of training steps per epoch
    STEPS_PER_EPOCH = 100

    # Skip detections with < 90% confidence
    DETECTION_MIN_CONFIDENCE = 0.9


# create model
model = mask_rcnn.MaskRCNN(num_classes=num_classes)


############################## training ###################################
def train():
    """Train the model."""
    # Training dataset.
    train_dataset = my_dataset.MyDataSet()
    train_dataset.load_balloon('data', 'train')
    train_dataset.prepare()

    # create data generator
    train_generator = data_generator(train_dataset, config=BalloonConfig(), shuffle=True,
                                     augmentation=None,
                                     batch_size=batch_size)

    # Validation dataset
    # dataset_train = my_dataset.MyDataSet()
    # dataset_train.load_balloon('data', 'val')
    # dataset_train.prepare()

    optimizer = tf.keras.optimizers.SGD(1e-3, momentum=0.9, nesterov=True)

    loss_history = []

    for epoch in range(100):

        for (batch, inputs) in enumerate(train_generator):

            batch_images, batch_image_meta, batch_gt_class_ids, batch_gt_boxes, batch_gt_masks = inputs

            # convert inputs to tensor
            # batch_images = tf.convert_to_tensor(batch_images, dtype=tf.float32)
            # batch_image_meta = tf.convert_to_tensor(batch_image_meta, dtype=tf.float32)
            # batch_gt_class_ids = tf.convert_to_tensor(batch_gt_class_ids, dtype=tf.int32)
            # batch_gt_boxes = tf.convert_to_tensor(batch_gt_boxes, dtype=tf.float32)
            # batch_gt_masks = tf.convert_to_tensor(batch_gt_masks, dtype=tf.bool)

            with tf.GradientTape() as tape:
                rpn_class_loss, rpn_bbox_loss, rcnn_class_loss, rcnn_bbox_loss, rcnn_mask_loss = model(
                    (batch_images, batch_image_meta, batch_gt_class_ids, batch_gt_boxes, batch_gt_masks),
                    training=True)

                total_loss = rpn_class_loss + rpn_bbox_loss + rcnn_class_loss + rcnn_bbox_loss + rcnn_mask_loss

            grads = tape.gradient(total_loss, model.trainable_variables)
            optimizer.apply_gradient(zip(grads, model.trainable_variables))
            loss_history.append(total_loss.numpy())

            if batch % 10 == 0:
                print('epoch', epoch, batch, np.mean(loss_history))


########################### testing #################################
# TWO THINGS ARE IMPORTANT, RPN ANCHOR REGRESSION AND ROI POOLING
# TODO FOR RPN, NMS NEED TO BE IMPLEMENTED FOR INTERVIEW
# proposals = model.simple_test_rpn(img, img_meta)
# STAGE 2 TESTING
# after proposals generated, next step is to cut roi region for roi pooling
# res = model.simple_test_bboxes(img, img_meta, proposals)

# visualize.display_instances(img, res['rois'], res['class_ids'], scores=res['scores'])
# plt.savefig('image_demo_ckpt.png')


##########################################################################
train()
