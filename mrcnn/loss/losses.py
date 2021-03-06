import tensorflow as tf


def rpn_class_loss(rpn_class_logits, target_matchs):
    '''RPN anchor classifier loss.

    Args
    ---
        target_matchs: [batch_size, num_anchors]. Anchor match type. 1=positive,
            -1=negative, 0=neutral anchor.
        rpn_class_logits: [batch_size, num_anchors, 2]. RPN classifier logits for FG/BG.
    '''

    # todo note here might be very straight, cos if the positive anchor only have 1 or 2,
    #  then the negative anchor would be much more than positive.

    # convert -1, +1 value to 0, 1
    anchor_class = tf.cast(tf.equal(target_matchs, 1), dtype=tf.int32)
    # Positive and Negative anchors contribute to the loss,
    # but neutral anchors (match value = 0) don't.
    indices = tf.where(tf.not_equal(target_matchs, 0))
    # Pick rows that contribute to the loss and filter out the rest.
    rpn_class_logits = tf.gather_nd(rpn_class_logits, indices)

    anchor_class = tf.gather_nd(anchor_class, indices)

    num_classes = rpn_class_logits.shape[-1]

    loss = tf.keras.losses.categorical_crossentropy(tf.one_hot(anchor_class, depth=num_classes), rpn_class_logits,
                                                    from_logits=True)

    loss = tf.reduce_mean(loss) if tf.size(loss) > 0 else tf.constant(0.0)
    return loss


def smooth_l1_loss(y_true, y_pred):
    '''Implements Smooth-L1 loss.

    当预测值与目标值相差很大时，L2 Loss的梯度为(x-t)，容易产生梯度爆炸
    L1 Loss的梯度为常数，通过使用Smooth L1 Loss，在预测值与目标值相差较大时，由L2 Loss转为L1 Loss可以防止梯度爆炸。
    Args
    ---
        y_true and y_pred are typically: [N, 4], but could be any shape.

    return: loss [N, 4]
    '''

    diff = tf.abs(y_true - y_pred)
    less_than_one = tf.cast(tf.less(diff, 1), dtype=tf.float32)

    loss = (less_than_one * 0.5 * diff ** 2) + (1 - less_than_one) * (diff - 0.5)
    return loss


def rpn_bbox_loss(rpn_deltas, target_deltas, target_matchs):
    '''
    Return the RPN bounding box loss graph.
    Args
    ---
        target_deltas: [batch, num_rpn_deltas, (dy, dx, log(dh), log(dw))].
            Uses 0 padding to fill in unsed rcnn deltas.
            IMPORTANT: target_deltas is only for pos anchors, and because we padding it when we generate them.
            So need to be trimmed
        target_matchs: [batch, anchors]. Anchor match type. 1=positive,
            -1=negative, 0=neutral anchor.
        rpn_deltas: [batch, anchors, (dy, dx, log(dh), log(dw))]
    '''

    def batch_trim(target_deltas, batch_count, batch_size):
        outputs = []

        for i in range(batch_size):
            outputs.append(target_deltas[i, :batch_count[i]])

        return tf.concat(outputs, axis=0)

    # rpn rcnn loss consists of only positive anchors
    pos_anchor_idx = tf.where(tf.equal(target_matchs, 1))

    pos_rpn_deltas = tf.gather_nd(rpn_deltas, pos_anchor_idx)

    # because rpn deltas is rpn output. shape is (Batch, anchors, 4)
    # however target deltas shape is [batch, num_rpn_deltas(256), 4], and only few positive, we need to trim the zeros
    # we need to trim the target deltas to same as pos_rpn deltas

    batch_count = tf.reduce_sum(tf.cast(tf.equal(target_matchs, 1), dtype=tf.int32), axis=1)  # [batch, 1]
    batch_size = target_deltas.shape.as_list()[0]
    # do batch trim to match the rpn_deltas
    target_deltas = batch_trim(target_deltas, batch_count, batch_size)  # [batch, pos_num, 4]

    loss = smooth_l1_loss(target_deltas, pos_rpn_deltas)

    loss = tf.reduce_mean(loss) if tf.size(loss) > 0 else tf.constant(0.0)

    return loss


def rcnn_bbox_loss(target_deltas_list, target_matchs_list, rcnn_deltas_list):
    '''Loss for Faster R-CNN bounding box refinement.
    note: this is only used in training, so target_matches_list depends on the target, maybe 256 default.
    but actually it is not certain value. maybe 192 or 134  etc. including pos and neg.

    rcnn_deltas_list: padded 256 in total for training use. maybe 0 pos_anchor.
    but need to figure out which pooled_roi and which class_id it cooresponding.

    Args
    ---
        target_deltas_list: list of [num_positive_rois, (dy, dx, log(dh), log(dw))]
        target_matchs_list: list of [num_rois]. Integer class IDs.
        rcnn_deltas_list: list of [num_rois, num_classes, (dy, dx, log(dh), log(dw))]
    '''
    target_matchs = tf.concat(target_matchs_list, axis=0)
    pos_anchor_idx = tf.where(tf.greater(target_matchs, 0))[:,0]

    target_deltas = tf.concat(target_deltas_list, axis=0)
    pos_target_deltas = tf.gather(target_deltas, pos_anchor_idx)

    rcnn_deltas = tf.concat(rcnn_deltas_list, axis=0) # 512

    # Only positive ROIs contribute to the loss. And only the right class_id of each ROI. Get their indicies.
    positive_roi_class_ids = tf.cast(tf.gather(target_matchs, pos_anchor_idx), dtype=tf.int32)
    indices = tf.stack([tf.cast(pos_anchor_idx, dtype=tf.int32), positive_roi_class_ids], axis=1)

    # Gather the deltas (predicted and true) that contribute to loss
    rcnn_deltas = tf.gather_nd(rcnn_deltas, indices)

    # smooth l1 loss
    loss = smooth_l1_loss(pos_target_deltas, rcnn_deltas)

    loss = tf.reduce_mean(loss) if tf.size(loss) > 0 else tf.constant(0.0)

    return loss


def rcnn_class_loss(rcnn_target_matchs_list, rcnn_class_logits_list):
    '''
    rcnn_target_matchs_list : list of [num_rois]. Integer class IDs. Uses zero padding to fill in the array.
    rcnn_class_logits_list : list of [num_rois, num_classes]
    '''

    class_ids = tf.concat(rcnn_target_matchs_list, axis=0)
    class_logits = tf.concat(rcnn_class_logits_list, axis=0)
    class_ids = tf.cast(class_ids, tf.int32)

    num_classes = tf.shape(rcnn_class_logits_list)[-1]

    loss = tf.keras.losses.categorical_crossentropy(tf.one_hot(class_ids, depth=num_classes), class_logits,
                                                    from_logits=True)

    loss = tf.reduce_mean(loss) if tf.size(loss) > 0 else tf.constant(0.0)

    return loss


def rcnn_mask_loss(target_mask_list, target_class_ids_list, mrcnn_mask_list):
    """Mask binary cross-entropy loss for the masks head.
    Params:
    -----------------------------------------------------------
        target_masks_list: [(num_rois, height, width),()....].
                        A float32 tensor of values 0 or 1. Uses zero padding to fill array.
        target_class_ids_list: [num_rois,...]. Integer class IDs. Zero padded.
        mrcnn_mask_list : [(num_rois, H, W, num_classes),()...]
    """
    target_masks = tf.concat(target_mask_list, axis=0)
    target_class_ids = tf.concat(target_class_ids_list, axis=0)
    pred_masks = tf.concat(mrcnn_mask_list, axis=0)

    # Reshape for simplicity. Merge first two dimensions into one.
    target_class_ids = tf.reshape(target_class_ids, (-1,)) # 512

    mask_shape = tf.shape(target_masks)  # batch*num_rois, h, w
    target_masks = tf.reshape(target_masks, (-1, mask_shape[1], mask_shape[2]))

    # num_rois, h, w, num_classes
    pred_shape = tf.shape(pred_masks)
    pred_masks = tf.reshape(pred_masks, (-1, pred_shape[1], pred_shape[2], pred_shape[3]))

    # Permute predicted masks to [N, num_classes, height, width]
    pred_masks = tf.transpose(pred_masks, [0, 3, 1, 2])

    # Only positive ROIs contribute to the loss. And only the class specific mask of each ROI.
    positive_roi_idx = tf.where(target_class_ids > 0)[:, 0]
    positive_roi_class_ids = tf.cast(tf.gather(target_class_ids, positive_roi_idx), dtype=tf.int32)
    indices = tf.stack([tf.cast(positive_roi_idx, dtype=tf.int32), positive_roi_class_ids], axis=1)

    # Gather the masks (predicted and true) that contribute to loss
    y_true = tf.gather(target_masks, positive_roi_idx)
    y_pred = tf.gather_nd(pred_masks, indices)  # cos pred_masks is nchw  choose no. first then choose class_id

    # Compute binary cross entropy.  If no positive ROIs, then return 0.
    loss = tf.nn.sigmoid_cross_entropy_with_logits(labels=y_true, logits=y_pred)

    loss = tf.reduce_mean(loss) if tf.size(loss) > 0 else tf.constant(0.0, dtype=tf.float32)

    return loss
