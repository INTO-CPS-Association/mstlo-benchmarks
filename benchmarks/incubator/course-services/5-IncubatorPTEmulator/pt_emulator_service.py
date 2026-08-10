
# Configure python path to load incubator modules
import sys
import os
import logging
import logging.config
import time
from scipy.integrate import solve_ivp
import numpy as np

# Get the current working directory. Should be 5-IncubatorPTEmulator
current_dir = os.getcwd()

assert os.path.basename(current_dir) == '5-IncubatorPTEmulator', 'Current directory is not 5-IncubatorPTEmulator'

# Get the parent directory. Should be the root of the repository
parent_dir = os.path.dirname(current_dir)

# The root of the repo should contain the incubator_dt folder. Otherwise something went wrong in 0-Pre-requisites.
assert os.path.exists(os.path.join(parent_dir, 'incubator_dt')), 'incubator_dt folder not found in the repository root'

incubator_dt_software_dir = os.path.join(parent_dir, 'incubator_dt', 'software')

assert os.path.exists(incubator_dt_software_dir), 'incubator_dt software directory not found'

# Add the parent directory to sys.path
sys.path.append(incubator_dt_software_dir)

from incubator.communication.server.rabbitmq import Rabbitmq
from incubator.communication.shared.protocol import ROUTING_KEY_STATE, ROUTING_KEY_HEATER

ROUTING_KEY_ROOM_TEMP = "routing.key.room.temperature"
ROUTING_KEY_LID = "routing.key.lid"

# Define the system of ODEs for the incubator
def incubator_ode(t, y, Ch, Cb, Ph, G_hb, G_br, Tr, H_h):
	Th, Tb = y  # Unpack the state variables (heater temp, box temp)
	
	# Differential equations
	dTh_dt = (H_h * Ph - G_hb * (Th - Tb)) / Ch
	dTb_dt = (G_hb * (Th - Tb) - G_br * (Tb - Tr)) / Cb
	
	return [dTh_dt, dTb_dt]


class PTEmulatorService:
	
	def __init__(self, execution_interval, Th_initial, Tb_initial, Ch, Cb, G_hb, G_br, Voltage, Current, T_room, rabbitmq_config):

		self._rabbitmq = Rabbitmq(**rabbitmq_config)
		self._l = logging.getLogger("PTEmulatorService")

		self._Th = Th_initial
		self._Tb = Tb_initial
		self._Ch = Ch
		self._Cb = Cb
		self._G_hb = G_hb
		self._G_br = G_br
		self._Voltage = Voltage
		self._Current = Current
		self._execution_interval = execution_interval # seconds
		self._T_room = T_room
		self._heater_on = 0.0
		self._lid_open = False

	def setup(self):
		self._rabbitmq.connect_to_server()

		# Declare local queues for the control commands
		self.heater_queue_name = self._rabbitmq.declare_local_queue(routing_key=ROUTING_KEY_HEATER)
		self.room_temp_queue_name = self._rabbitmq.declare_local_queue(routing_key=ROUTING_KEY_ROOM_TEMP)
		self.lid_queue_name = self._rabbitmq.declare_local_queue(routing_key=ROUTING_KEY_LID)

		self._l.info(f"PTEmulatorService setup complete.")
		
	def _try_read_lid_control(self):
		msg = self._rabbitmq.get_message(self.lid_queue_name)
		if msg is not None:
			self._lid_open = msg["lid_open"]
			return msg["lid_open"]
		else:
			return None

	def _try_read_heat_control(self):
		msg = self._rabbitmq.get_message(self.heater_queue_name)
		if msg is not None:
			return msg["heater"]
		else:
			return None
		
	def _try_read_room_temp(self):
		msg = self._rabbitmq.get_message(self.room_temp_queue_name)
		if msg is not None:
			return msg["temperature"]
		else:
			return None

	def check_control_commands(self):
		# Check if there are control commands
		heat_cmd = self._try_read_heat_control()
		room_temp = self._try_read_room_temp()
		lid_cmd = self._try_read_lid_control()
		
		if heat_cmd is not None:
			self._l.debug(f"Heat command: on={heat_cmd}")
			self._heater_on = 1.0 if heat_cmd else 0.0
		if room_temp is not None:
			self._l.debug(f"Room temperature command: {room_temp}")
			self._T_room = room_temp
		if lid_cmd is not None:
			self._l.debug(f"Lid command: open={lid_cmd}")
			self._G_br = self._G_br*10 if lid_cmd else self._G_br/10

	def emulate_pt(self):
		# Emulate the PT behavior. This is very similar to the fmi2DoStep implemented in previous notebooks.

		state = [self._Th, self._Tb]  # Initial state

		# Solve the ODE over a small time window of self._execution_interval seconds, starting from time 0
		sol = solve_ivp(
			lambda t, y: incubator_ode(t, y, self._Ch, self._Cb, self._Voltage*self._Current, self._G_hb, self._G_br, self._T_room, self._heater_on),
			[0.0, self._execution_interval], state, t_eval=np.linspace(0.0, self._execution_interval, 2))
		
		# Update the state variables
		self._Th = sol.y[0, -1] + np.random.normal(0, 0.1)
		self._Tb = sol.y[1, -1] + np.random.normal(0, 0.1)

	def send_state(self, time_start):
		timestamp = time.time_ns()
		# Publishes the new state
		message = {
			"measurement": "emulator",
			"time": timestamp,
			"tags": {
				"source": "emulator"
			},
			"fields": {
				"t1": self._Tb,
				"time_t1": timestamp,
				"t2": self._Tb,
				"time_t2": timestamp,
				"t3": self._T_room,
				"time_t3": timestamp,
				"average_temperature": self._Tb,
				"heater_on": self._heater_on > 0.5,
				"fan_on": True,
				"execution_interval": self._execution_interval,
				"elapsed": time.time() - time_start,
				"lid_open": self._lid_open
			}
		}

		self._rabbitmq.send_message(ROUTING_KEY_STATE, message)
		self._l.debug(f"Message sent to {ROUTING_KEY_STATE}.")
		self._l.debug(message)
	
	def start_emulation(self):
		# Start the emulation loop
		self._l.info("Starting PTEmulator emulation loop.")
		while True:
			time_start = time.time()
			# Check if there are control commands
			self.check_control_commands()
			# Emulate the PT behavior
			self.emulate_pt()
			# Send the new state to the incubator physical twin
			self.send_state(time_start)
			# Sleep until the next sample
			time_end = time.time()
			time_diff = time_end - time_start
			if time_diff < self._execution_interval:
				time.sleep(self._execution_interval - time_diff)
			else:
				self._l.warning(f"Emulation loop took too long: {time_diff} seconds.")
	
if __name__ == "__main__":
	# Get utility functions to config logging and load configuration
	from incubator.config.config import load_config
	from pyhocon import ConfigFactory
	
	# Get logging configuration
	logging.config.fileConfig("logging.conf")

	# Get path to the startup.conf file used in the incubator dt:
	startup_conf = os.path.join(os.path.dirname(os.getcwd()), 'incubator_dt', 'software','startup.conf')
	assert os.path.exists(startup_conf), 'startup.conf file not found'

	# The startup.conf comes from the incubator dt repository.
	config = ConfigFactory.parse_file(startup_conf)
	
	service = PTEmulatorService(
		execution_interval = 3.0,
		Th_initial = 30.0,
		Tb_initial = 30.0,
		Ch = 300.0,
		Cb = 200.0,
		G_hb = 1.6,
		G_br = 0.57,
		Voltage = 12.0,
		Current = 1.5,
		T_room = 20.0,
		rabbitmq_config=config["rabbitmq"])

	service.setup()
	
	# Start the PTEmulatorService
	service.start_emulation()
