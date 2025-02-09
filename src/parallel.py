from __future__ import division
import math
from multiprocessing import Process, Queue, JoinableQueue, Value
from threading import Thread
from functools import partial
import numpy as np

class ParallelBatchIterator(object):
	"""
	Uses a producer-consumer model to prepare batches on the CPU in different processes or threads (while you are training on the GPU).

	Constructor arguments:
		batch_generator: function which can be called to yield a new batch.
		X: input for the batch_generator (could be for instance filenames)
		
		ordered: boolean (default=False), whether the order of the batches matters
		batch_size: integer (default=1), amount of points in one batch
		
		multiprocess: boolean (default=True), multiprocess instead of multithrea
		n_producers: integer (default=4), amount of producers (threads or processes)
		max_queue_size: integer (default=4*n_producers)
	"""

	def __init__(self, batch_generator, X, batch_size=1, ordered=False, multiprocess=True, n_producers=4, max_queue_size=None):
		self.generator = batch_generator
		self.ordered = ordered
		self.multiprocess = multiprocess
		self.n_producers = n_producers
		self.X = X
		self.batch_size = batch_size

		if max_queue_size is None:
			self.max_queue_size = n_producers*4
		else:
			self.max_queue_size = max_queue_size

	def __call__(self):
		return self

	def __iter__(self):
		queue = JoinableQueue(maxsize=self.max_queue_size)

		n_batches, job_queue = self._start_producers(queue)

		# Run as consumer (read items from queue, in current thread)
		for x in xrange(n_batches):
			item = queue.get()
			if item is not None:
				yield item # Yield the item to the consumer (user)
			queue.task_done()

		queue.close()
		job_queue.close()
		
	def __len__(self):
		return math.ceil(len(self.X)/self.batch_size)

	def _start_producers(self, result_queue):
		jobs = Queue()
		n_workers = self.n_producers
		batch_count = 0

		# Flag used for keeping values in queue in order
		last_queued_job = Value('i', -1)
		
		chunks = _chunks(self.X,self.batch_size)
		

		# Add jobs to queue
		for job_index, X_batch in enumerate(chunks):
			batch_count += 1
			jobs.put( (job_index,X_batch) )
			
		# Add poison pills to queue (to signal workers to stop)
		for i in xrange(n_workers):
			jobs.put((-1,None))

		# Define producer function
		produce = partial(_produce_helper,
			generator=self.generator,
			jobs=jobs,
			result_queue=result_queue,
			last_queued_job=last_queued_job,
			ordered=self.ordered)

		# Start worker processes or threads
		for i in xrange(n_workers):
			name = "ParallelBatchIterator worker {0}".format(i)
		
			if self.multiprocess:
				p = Process(target=produce, args=(i,), name=name)
			else:
				p = Thread(target=produce, args=(i,), name=name)

			# Make the process daemon, so the main process can die without these finishing
			p.daemon = True
			p.start()

		return batch_count, jobs

def _produce_helper(id, generator, jobs, result_queue, last_queued_job, ordered):
	"""
		What one worker executes, defined as a top level function as this is required for the Windows platform.
	"""
	np.random.seed()
	while True:
		job_index, task = jobs.get()

		# Kill the worker if there is no more work
		# (This is a poison pill)
		if job_index == -1 and task is None:
			break

		try:
			result = generator(task)
		except:
			print "Producer failed, skipping"
			result = None

		# Put result onto the 'done'-queue
		while True:
			# My turn to add job result (to keep it in order)?
			if not ordered or last_queued_job.value == job_index-1:
				with last_queued_job.get_lock():
					result_queue.put(result)
					last_queued_job.value += 1
					break
		

def _chunks(l, n):
    """ Yield successive n-sized chunks from l.
        from http://goo.gl/DZNhk
    """
    for i in xrange(0, len(l), n):
        yield l[i:i+n]
