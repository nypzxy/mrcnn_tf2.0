import tensorflow as tf


class AnchorGenerator():
    """
       This class operate on padded iamge, eg. [1216, 1216]
       and generate scales*ratios number of anchor boxes for each point in
       padded image, with stride = feature_strides
       number of anchor = (1216 // feature_stride)^2
       number of anchor boxes = number of anchor * (scales_len*ratio_len)
       """

    def __init__(self,
                 scales=(32, 64, 128, 256, 512),
                 ratios=(0.5, 1, 2),
                 feature_strides=(4, 8, 16, 32, 64)):
        '''
        Anchor Generator

        Attributes
        ---
            scales: 1D array of anchor sizes in pixels. eg 8, 16, 32, 64, 128
            ratios: 1D array of anchor ratios of width/height. 0.5, 1, 2
            feature_strides: Stride of the feature map relative to the image in pixels. 4, 8, 16, 32, 64
        '''

        self.scales = scales
        self.ratios = ratios
        self.feature_strides = feature_strides

    def generate_pyramid_anchors(self, image_shape):
        """Generate anchor at different levels of a feature pyramid. Each scale
        is associated with a level of the pyramid, but each ratio is used in
        all levels of the pyramid.

        Returns:
        anchor: [N, (y1, x1, y2, x2)]. All generated anchor in one array. Sorted
            with the same order of the given scales. So, anchor of scale[0] come
            first, then anchor of scale[1], and so on.
        """
        # Anchors
        # [anchor_count, (y1, x1, y2, x2)]

        # generate anchor
        feature_shapes = [(image_shape[0] // stride, image_shape[1] // stride)
                          for stride in self.feature_strides]

        anchors = [
            self._generate_level_anchors(level, feature_shape)
            for level, feature_shape in enumerate(feature_shapes)
        ]

        anchors = tf.concat(anchors, axis=0)
        anchors = tf.stop_gradient(anchors)

        return anchors

    def _generate_level_anchors(self, level, feature_shape):
        scale = self.scales[level]
        ratios = self.ratios
        feature_stride = self.feature_strides[level]

        # Get all combinations of scales and ratios
        scales, ratios = tf.meshgrid([float(scale)], ratios)
        scales = tf.reshape(scales, [-1])  # [8, 8, 8]
        ratios = tf.reshape(ratios, [-1])  # [0.5, 1, 2]

        # Enumerate heights and widths from scales and ratios
        heights = scales / tf.sqrt(ratios)
        widths = scales * tf.sqrt(ratios)

        # Enumerate shifts in feature space, [0, 4, ..., 512-4]
        shifts_y = tf.multiply(tf.range(feature_shape[0]), feature_stride)
        shifts_x = tf.multiply(tf.range(feature_shape[1]), feature_stride)

        shifts_x, shifts_y = tf.cast(shifts_x, tf.float32), tf.cast(shifts_y, tf.float32)
        shifts_x, shifts_y = tf.meshgrid(shifts_x, shifts_y)

        # Enumerate combinations of shifts, widths, and heights
        box_widths, box_centers_x = tf.meshgrid(widths, shifts_x)
        box_heights, box_centers_y = tf.meshgrid(heights, shifts_y)

        # Reshape to get a list of (y, x) and a list of (h, w)
        box_centers = tf.reshape(tf.stack([box_centers_y, box_centers_x], axis=-1), (-1, 2))
        box_sizes = tf.reshape(tf.stack([box_heights, box_widths], axis=-1), (-1, 2))

        # Convert to corner coordinates (N, (y1, x1, y2, x2))
        boxes = tf.concat([box_centers - 0.5 * box_sizes,
                           box_centers + 0.5 * box_sizes], axis=1)

        return boxes