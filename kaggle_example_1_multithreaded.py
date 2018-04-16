from keras.preprocessing.image import ImageDataGenerator
from keras.models import Sequential
from keras.layers import Conv2D, MaxPooling2D
from keras.layers import Activation, Dropout, Flatten, Dense
from keras import backend as K

from timeit import default_timer as timer
import time
import os
import sys

from progress.bar import Bar

class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._original_stdout

# dimensions of our images.
img_width, img_height = 150, 150

train_data_dir = 'data/train'
validation_data_dir = 'data/validation'
nb_train_samples = 20000
nb_validation_samples = 5000
epochs = 100
batch_size = 16
threads=2

train_batches = nb_validation_samples // batch_size
validation_batches = nb_validation_samples // batch_size

if K.image_data_format() == 'channels_first':
    input_shape = (3, img_width, img_height)
else:
    input_shape = (img_width, img_height, 3)

model = Sequential()

model.add(Conv2D(64, (3, 3), input_shape=input_shape))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(2, 2)))

model.add(Conv2D(64, (3, 3)))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(2, 2)))

model.add(Conv2D(128, (3, 3)))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(2, 2)))

model.add(Flatten())
model.add(Dense(128))
model.add(Activation('relu'))
model.add(Dropout(0.8))
model.add(Dense(1))
model.add(Activation('sigmoid'))

model.compile(loss='binary_crossentropy',
              optimizer='rmsprop',
              metrics=['accuracy'])

print(model.summary())

import multiprocessing as mp

output_queues = [mp.Queue() for _ in range(threads)]

def get_datasets(x, output_queues):
    train_datagen = ImageDataGenerator(
        rescale=1. / 255,
        shear_range=0.2,
        zoom_range=0.2,
        horizontal_flip=True)

    test_datagen = ImageDataGenerator(rescale=1. / 255)

    with HiddenPrints():
        train_generator = train_datagen.flow_from_directory(
            train_data_dir,
            target_size=(img_width, img_height),
            batch_size=batch_size,
            class_mode='binary')

    # continue adding batches until
    counter = 0
    for x_train, y_train in train_generator:
        output_queues[x % threads].put([x_train, y_train])
        counter += 1
        if counter >= train_batches:
            break

    with HiddenPrints():
        validation_generator = test_datagen.flow_from_directory(
            validation_data_dir,
            target_size=(img_width, img_height),
            batch_size=batch_size,
            class_mode='binary')

    # continue adding batches until
    counter = 0
    for x_val, y_val in validation_generator:
        output_queues[x % threads].put([x_val, y_val])
        counter += 1
        if counter >= validation_batches:
            break

    return True

processes = [mp.Process(target=get_datasets, args=(x, output_queues)) for x in range(len(output_queues))]
for process in processes:
    process.start()

current_output = 0
for e in range(epochs):
    print('Epoch', e+1)
    start = timer()

    batches = 0
    current_queue = output_queues[current_output%threads]

    bar = Bar('Batches', max=train_batches, suffix='[%(index)d/%(max)d] %(eta)dsec')

    train_loss, train_acc = 0, 0
    for batch_id in range(train_batches):
        while current_queue.empty():
            time.sleep(0.1)

        x_train, y_train = current_queue.get()

        result = model.fit(x_train, y_train, verbose=0, batch_size=batch_size)
        bar.next()

        train_loss += result.history['loss'][0]
        train_acc += result.history['acc'][0]

    bar.finish()

    result = model.evaluate_generator((current_queue.get() for _ in range(validation_batches)), steps=validation_batches)

    process = processes.pop(0)
    process.terminate()

    processes.append(mp.Process(target=get_datasets, args=(current_output % threads, output_queues)))
    processes[-1].start()

    current_output += 1
    end = timer()

    print('train_loss: {:.4f} | train_acc: {:.4f} | test_loss: {:.4f} | test_acc: {:.4f} | epoch_time: {:.1f}'.format(train_loss/train_batches,
                                                                                   train_acc/train_batches,
                                                                                   result[0],
                                                                                   result[1],
                                                                                   end-start))

model.save_weights('monster.h5')