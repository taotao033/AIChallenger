import tensorflow as tf
from tensorflow.python.estimator.canned import optimizers

class TextCNN(tf.estimator.Estimator):
  def __init__(self, params, model_dir=None, config=None, optimizer='Adagrad', warm_start_from=None):
    self.optimizer = optimizers.get_optimizer_instance(optimizer, params.learning_rate)
    def _model_fn(features, labels, mode, config):
      sentence = features['content']
      sentence_len = sentence.get_shape().as_list()[1]
      # Get word embeddings for each token in the sentence
      embeddings = tf.get_variable(name="embeddings", dtype=tf.float32,
                                   shape=[params.vocab_size, params.embedding_size])
      sentence = tf.nn.embedding_lookup(embeddings, sentence)  # shape:(batch, sentence_len, embedding_size)
      # add a channel dim, required by the conv2d and max_pooling2d method
      sentence = tf.expand_dims(sentence, -1)  # shape:(batch, sentence_len/height, embedding_size/width, channels=1)

      pooled_outputs = []
      for filter_size in params.filter_sizes:
        conv = tf.layers.conv2d(
          sentence,
          filters=params.num_filters,
          kernel_size=[filter_size, params.embedding_size],
          strides=(1, 1),
          padding="VALID",
          activation=tf.nn.relu)
        pool = tf.layers.max_pooling2d(
          conv,
          pool_size=[sentence_len - filter_size + 1, 1],
          strides=(1, 1),
          padding="VALID")
        pooled_outputs.append(pool)
      h_pool = tf.concat(pooled_outputs, 3)  # shape: (batch, 1, len(filter_size) * embedding_size, 1)
      net = tf.reshape(h_pool, [-1, params.num_filters * len(params.filter_sizes)])  # shape: (batch, len(filter_size) * embedding_size)
      # Build the hidden layers, sized according to the 'hidden_units' param.
      for units in params.hidden_units:
        net = tf.layers.dense(net, units=units, activation=tf.nn.relu)
        if params.dropout_rate > 0.0:
          net = tf.layers.dropout(net, params.dropout_rate, training=(mode == tf.estimator.ModeKeys.TRAIN))
      metrics = {}
      predictions = {}
      loss = 0
      for k, v in labels.iteritems():
        one_logits = tf.layers.dense(net, params.num_classes, activation=None)
        loss += tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=one_logits, labels=v), name=k+"_loss")
        predictions[k] = tf.argmax(one_logits, 1)
        acc_key = k + "_accuracy"
        metrics[acc_key] = tf.metrics.accuracy(labels=v, predictions=predictions[k])
        tf.summary.scalar(acc_key, metrics[acc_key][1])
      if mode == tf.estimator.ModeKeys.PREDICT:
        return tf.estimator.EstimatorSpec(mode, predictions=predictions)
      if mode == tf.estimator.ModeKeys.EVAL:
        return tf.estimator.EstimatorSpec(mode, loss=loss, eval_metric_ops=metrics)
      assert mode == tf.estimator.ModeKeys.TRAIN
      train_op = self.optimizer.minimize(loss, global_step=tf.train.get_global_step())
      return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)

    super(TextCNN, self).__init__(
        model_fn=_model_fn, model_dir=model_dir, config=config,
        warm_start_from=warm_start_from)