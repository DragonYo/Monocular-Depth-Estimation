#encoding: utf-8

from datetime import datetime
from tensorflow.python.platform import gfile as directoryHandler
import numpy as np
import tensorflow as tf
from dataset import DataSet
from dataset import output_predictions_into_images
#import model as model
import new_model as model
import train_operation as trainOperation

MAX_EPOCH = 1000
LOG_DEVICE_PLACEMENT = False
BATCH_SIZE = 8
TRAIN_FILE = "data/train.csv"
COARSE_DIR = "coarse_checkpoints"
REFINE_DIR = "refine_checkpoints"

REFINE_TRAIN = True
FINE_TUNE = True


def train():
    with tf.Graph().as_default():
        global_step = tf.Variable(0, trainable=False)
        dataset = DataSet(BATCH_SIZE)
        images, depths, invalid_depths = dataset.create_trainingbatches_from_csv(TRAIN_FILE)
        keep_conv = tf.placeholder(tf.float32)
        keep_hidden = tf.placeholder(tf.float32)
        
        if REFINE_TRAIN:
            print("refine train.")
            coarse = model.globalDepthMap(images, keep_conv, trainable=False)
            
            logits, f3_d, f3, f2, f1_d, f1, pf1 = model.localDepthMap(images, coarse, keep_conv, keep_hidden)
            
            o_p_logits = tf.Print(logits, [logits], summarize=100)
            o_p_f3_d = tf.Print(f3_d, [f3_d], "fine3_dropout", summarize=100)
            o_p_f3 = tf.Print(f3, [f3], "fine3", summarize=100)
            o_p_f2 = tf.Print(f2, [f2], "fine2", summarize=100)
            o_p_f1_d = tf.Print(f1_d, [f1_d], "fine1_dropout", summarize=100)
            o_p_f1 = tf.Print(f1, [f1], "fine1", summarize=100)
            o_p_pf1 = tf.Print(pf1, [pf1], "pre_fine1", summarize=100)
        else:
            print("coarse train.")
            logits = model.globalDepthMap(images, keep_conv, keep_hidden)
        loss = model.loss(logits, depths, invalid_depths)
        train_op = trainOperation.train(loss, global_step, BATCH_SIZE)
        
        # Tensorboard
        #merged = tf.summary.merge_all()
        writer = tf.summary.FileWriter("/tmp/graph_data/train")
        
        # Initialize all Variables
        init_op = tf.global_variables_initializer()

        # Session
        sess = tf.Session(config=tf.ConfigProto(log_device_placement=LOG_DEVICE_PLACEMENT))
        writer.add_graph(sess.graph)
        sess.run(init_op)    

        # parameters
        coarse_params = {}
        refine_params = {}
        if REFINE_TRAIN:
            for variable in tf.global_variables():
                variable_name = variable.name
                print("parameter: %s" % (variable_name))
                if variable_name.find("/") < 0 or variable_name.count("/") != 1:
                    continue
                if variable_name.find('coarse') >= 0:
                    coarse_params[variable_name] = variable
                print("parameter: %s" %(variable_name))
                if variable_name.find('fine') >= 0:
                    refine_params[variable_name] = variable
        else:
            for variable in tf.trainable_variables():
                variable_name = variable.name
                print("parameter: %s" %(variable_name))
                if variable_name.find("/") < 0 or variable_name.count("/") != 1:
                    continue
                if variable_name.find('coarse') >= 0:
                    coarse_params[variable_name] = variable
                if variable_name.find('fine') >= 0:
                    refine_params[variable_name] = variable
        # define saver
        print(coarse_params)
        saver_coarse = tf.train.Saver(coarse_params)
        if REFINE_TRAIN:
            saver_refine = tf.train.Saver(refine_params)
        # fine tune
        if FINE_TUNE:
            coarse_ckpt = tf.train.get_checkpoint_state(COARSE_DIR)
            if coarse_ckpt and coarse_ckpt.model_checkpoint_path:
                print("Pretrained coarse Model Loading.")
                saver_coarse.restore(sess, coarse_ckpt.model_checkpoint_path)
                print("Pretrained coarse Model Restored.")
            else:
                print("No Pretrained coarse Model.")
            if REFINE_TRAIN:
                print("trying to load models")
                refine_ckpt = tf.train.get_checkpoint_state(REFINE_DIR)
                print(refine_ckpt)
                if refine_ckpt and refine_ckpt.model_checkpoint_path:
                    print("Pretrained refine Model Loading.")
                    saver_refine.restore(sess, refine_ckpt.model_checkpoint_path)
                    print("Pretrained refine Model Restored.")
                else:
                    print("No Pretrained refine Model.")

        # train
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess=sess, coord=coord)
        for step in range(MAX_EPOCH):
            index = 0
            for i in range(1000):
                _, loss_value, logits_val, images_val, depths_val, _, _, = sess.run([train_op, loss, logits, images, depths, o_p_logits, o_p_f3_d], feed_dict={keep_conv: 0.8, keep_hidden: 0.5})
                #_, loss_value, logits_val, images_val, summary = sess.run([train_op, loss, logits, images, merged], feed_dict={keep_conv: True, keep_hidden: True})
                #writer.add_summary(summary, step)
                if index % 100 == 0:
                    print("%s: %d[epoch]: %d[iteration]: train loss %f" % (datetime.now(), step, index, loss_value))
                    assert not np.isnan(loss_value), 'Model diverged with loss = NaN'
                if index % 100 == 0:
                    if REFINE_TRAIN:
                        output_predictions_into_images(logits_val, images_val, depths_val, "data/predict_refine_%05d_%05d" % (step, i))
                    else:
                        output_predictions_into_images(logits_val, images_val, depths_val, "data/predict_%05d_%05d" % (step, i))
                index += 1

            if step % 5 == 0 or (step * 1) == MAX_EPOCH:
                if REFINE_TRAIN:
                    refine_checkpoint_path = REFINE_DIR + '/model.ckpt'
                    saver_refine.save(sess, refine_checkpoint_path, global_step=step)
                else:
                    coarse_checkpoint_path = COARSE_DIR + '/model.ckpt'
                    saver_coarse.save(sess, coarse_checkpoint_path, global_step=step)
        coord.request_stop()
        coord.join(threads)
        sess.close()


def main(args=None):
    createCheckpointDirectorys()
    train()


def createCheckpointDirectorys():
    if not directoryHandler.Exists(COARSE_DIR):
        directoryHandler.MakeDirs(COARSE_DIR)
    if not directoryHandler.Exists(REFINE_DIR):
        directoryHandler.MakeDirs(REFINE_DIR)


if __name__ == '__main__':
    tf.app.run()
    