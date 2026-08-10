## 0. Terminal & Processes (`0-TerminalAndProcesses.md`)

### A. Basic terminal fluency

1. Navigate to a directory of your choice using the terminal.
2. Create a directory called `exercise_terminal`.
3. Inside it, create two empty files: `a.txt` and `b.txt`.
4. List the files and verify they exist.
5. Remove only `b.txt` from the terminal.


### B. Processes and concurrency

1. Create a Python script that prints a message every second.
2. Run the script in a terminal.
3. Open a second terminal and:

   * List all running Python processes.
   * Identify the PID of your script.
4. Terminate the script *without* closing the terminal window.


### C. Background processes (stretch)

1. Run a Python script in the background.
2. Verify it is still running after closing the terminal tab.
3. Stop it explicitly.


## 1. Git (`1-Git.ipynb`)

### A. Repository basics

1. Create a new directory and initialize a Git repository.
2. Create a file `notes.md` and add some text.
3. Check the repository status.
4. Commit the file with a meaningful commit message.


### B. Commit history and changes

1. Modify `notes.md` twice, committing after each change.
2. Inspect the commit history.
3. Show the difference between the last two commits.


### C. Branching (important mental model)

1. Create a new branch called `experiment`.
2. Make a change in that branch and commit it.
3. Switch back to `main` (or `master`).
4. Merge `experiment` into `main`.

**Reflection question:**
What happens to the commit history after the merge?


## 2. Docker (`2-Docker.ipynb`, `Dockerfile`, `hello.py`)



### A. Running containers

1. Pull a minimal Linux image.
2. Start a container and open a shell inside it.
3. Inspect the filesystem of the container.
4. Exit the container and verify it stopped.


### B. Building images

1. Inspect the provided `Dockerfile`.
2. Build a Docker image from it.
3. Run the container and observe the output (`Hello from Docker!`).
4. Modify `hello.py` to print a different message and rebuild the image.


### C. Containers vs host

1. Add a file to the container filesystem.
2. Stop and remove the container.
3. Start a new container from the same image.
4. Check whether the file still exists.

**Reflection:**
Why does this happen?


## 3. RabbitMQ (`3-RabbitMQ.ipynb`, `send.py`)



### A. Message sending

1. Start RabbitMQ (via Docker or local install).
2. Run the provided `send.py`.
3. Verify that a message is sent successfully.


### B. Writing a consumer

1. Write a Python script that:

   * Connects to RabbitMQ
   * Subscribes to the same queue
   * Prints received messages
2. Run the consumer first, then run `send.py`.


### C. Multiple consumers

1. Run two consumer scripts simultaneously.
2. Send multiple messages.
3. Observe how messages are distributed.

**Reflection question:**
What happens if one consumer is much slower than the other?


## 4. InfluxDB (`4-InfluxDB.ipynb`)

### A. Database basics

1. Start InfluxDB.
2. Create a bucket for experimental data.
3. Insert at least 5 data points manually (e.g., temperature values).


### B. Querying data

1. Write a query that retrieves:

   * All values
   * Only the last value
2. Modify the query to filter by time range.


### C. Python integration

1. Write a Python script that:

   * Writes a timestamped value every 5 seconds
2. Let it run for at least 1 minute.
3. Query the data and visualize it (simple table is enough).

**Stretch:**
What happens if the script crashes and restarts?


## 5. Integration exercises

### A. Docker + Python

1. Dockerize a Python script that runs indefinitely.
2. Verify it restarts correctly after stopping the container.


### B. RabbitMQ + Docker

1. Run RabbitMQ in Docker.
2. Run a producer on the host.
3. Run a consumer in a container.

### C. RabbitMQ → InfluxDB pipeline (advanced)

1. Producer sends sensor-like messages (timestamp + value).
2. Consumer receives messages and writes them to InfluxDB.
3. Query InfluxDB to confirm data arrival.
