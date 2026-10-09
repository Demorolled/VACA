# 🔌 IoT & Embedded Systems

> Reference for building IoT and embedded applications — device architecture, communication protocols, RTOS patterns, and edge computing.
> Extracted from The Programming Bible's IoT/Embedded Deep level.

---

## 1. IoT Architecture (4-Layer Model)

```
┌─────────────────────────────────────────────┐
│       APPLICATION LAYER                       │
│  Dashboards, Mobile Apps, Analytics, UI       │
├─────────────────────────────────────────────┤
│       MIDDLEWARE LAYER                        │
│  IoT Cloud, Message Brokers, Edge Computing   │
│  AWS Greengrass, Azure IoT Edge               │
├─────────────────────────────────────────────┤
│       NETWORK LAYER                           │
│  BLE, LoRaWAN, WiFi, 6LoWPAN, Zigbee         │
├─────────────────────────────────────────────┤
│       PERCEPTION LAYER                        │
│  Sensors, Actuators, MCUs (ARM, RISC-V, ESP32)│
└─────────────────────────────────────────────┘
```

### Device Architecture

```
┌──────────────────────────────────────┐
│          IoT DEVICE                   │
│                                        │
│  ┌────────┐  ┌────────┐  ┌────────┐  │
│  │ Sensor │  │ MCU    │  │ Radio  │  │
│  │ (input)│─▶│ (logic)│─▶│ (net)  │  │
│  └────────┘  └───┬────┘  └────────┘  │
│                  │                    │
│           ┌──────▼──────┐            │
│           │  Actuator   │            │
│           │  (output)   │            │
│           └─────────────┘            │
└──────────────────────────────────────┘
```

---

## 2. IoT Communication Protocols

### Protocol Selection Matrix

| Protocol | Range | Bandwidth | Power | Use Case |
|---|---|---|---|---|
| **BLE** | 10-100m | 1-2 Mbps | Very low | Wearables, beacons, sensors |
| **LoRaWAN** | 2-15km | 0.3-50 kbps | Very low | Agriculture, smart city, tracking |
| **Zigbee** | 10-100m | 250 kbps | Low | Home automation, mesh networks |
| **WiFi** | 30-100m | 54-900 Mbps | High | High-bandwidth devices |
| **Thread** | 30-100m | 250 kbps | Low | Mesh, Matter protocol |
| **Cellular** | Global | 10-1000 Mbps | High | Vehicles, wide-area |
| **NFC/RFID** | <10cm | 106-848 kbps | Passive | Payments, access control |

### MQTT Protocol (Primary IoT Protocol)

```
┌──────┐  Subscribe(topic)  ┌──────┐
│Client├───────────────────▶│Broker│
│  A   │                    │      │
└──┬───┘                    │      │
   │                        │      │
   └──Publish(topic/data)───▶      │
                              │    │
                    ┌─────────┘    │
                    │Publish(topic)│
                    ▼              ▼
                 ┌──────┐     ┌──────┐
                 │Client│     │Client│
                 │  B   │     │  C   │
                 └──────┘     └──────┘
```

**Topic Structure:** `device/{id}/telemetry` — hierarchical, supports wildcards
- `+` = single-level wildcard: `device/+/telemetry`
- `#` = multi-level wildcard: `device/#`

**Quality of Service Levels:**

| QoS | Level | Guarantee | Overhead | Use Case |
|---|---|---|---|---|
| **QoS 0** | At most once | Fire-and-forget | Minimal | Telemetry, non-critical data |
| **QoS 1** | At least once | PUBACK, may duplicate | Medium | Commands, sensor readings |
| **QoS 2** | Exactly once | 4-way handshake | Highest | Financial, critical control |

### MQTT Client Implementation

```python
"""MQTT client for IoT device communication."""
import json
import asyncio
from typing import Callable, Any
try:
    import aiomqtt
except ImportError:
    import paho.mqtt.client as mqtt

class IoTDeviceClient:
    """Generic MQTT client for IoT devices."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.handlers: dict[str, list[Callable]] = {}

        self.client = mqtt.Client(client_id=client_id)
        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to MQTT broker at {self.broker_host}")
            # Re-subscribe after reconnect
            for topic in self.handlers:
                client.subscribe(topic)
        else:
            print(f"Connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
            for handler in self.handlers.get(topic, []):
                handler(payload)
        except json.JSONDecodeError:
            for handler in self.handlers.get(topic, []):
                handler(msg.payload)

    def connect(self):
        self.client.connect(self.broker_host, self.broker_port)
        self.client.loop_start()

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic: str, data: dict, qos: int = 0, retain: bool = False):
        payload = json.dumps(data)
        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Publish failed: {result.rc}")

    def subscribe(self, topic: str, handler: Callable, qos: int = 0):
        if topic not in self.handlers:
            self.handlers[topic] = []
            self.client.subscribe(topic, qos=qos)
        self.handlers[topic].append(handler)

    def send_telemetry(self, device_id: str, temperature: float, **kwargs):
        self.publish(
            f"device/{device_id}/telemetry",
            {"temp": temperature, **kwargs},
            qos=0,  # Sensor data — fire-and-forget
        )

    def send_command_ack(self, device_id: str, command_id: str, status: str):
        self.publish(
            f"device/{device_id}/status",
            {"cmd": command_id, "status": status},
            qos=2,  # Acknowledgment — exactly once
        )


# Usage example
device = IoTDeviceClient(broker_host="iot.eclipse.org")
device.connect()

device.subscribe("device/my-sensor/commands", lambda msg: print(f"Command: {msg}"))
device.send_telemetry("my-sensor", temperature=22.5, humidity=60, battery=85)
```

---

## 3. Real-Time Operating System (RTOS) Patterns

### RTOS Kernel Types

| Type | Preemption | Determinism | Complexity |
|---|---|---|---|
| **Preemptive** | Scheduler can interrupt any task | High | Medium |
| **Cooperative** | Tasks must yield control voluntarily | Low | Simple |
| **Hybrid** | Both preemptive and cooperative zones | Medium | High |

### Task Management

```
Task States:
                    
        ┌─────────┐
        │ Dormant │
        └────┬────┘
             │ create
             ▼
        ┌─────────┐
   ┌───▶│  Ready  │◀────────────┐
   │    └────┬────┘              │
   │         │ scheduler         │
   │         ▼                   │
   │    ┌─────────┐   preempt    │
   │    │ Running │──────────────┤
   │    └────┬────┘              │
   │         │ wait/block        │
   │         ▼                   │
   │    ┌─────────┐   signal     │
   │    │ Blocked │──────────────┘
   │    └────┬────┘
   │         │ suspend
   │         ▼
   │    ┌───────────┐
   └────│ Suspended │
        └───────────┘
```

### Task Control Block (TCB)

```c
// Minimal RTOS TCB structure
typedef struct {
    uint32_t *sp;           // Stack pointer
    uint32_t *stack_base;   // Bottom of stack
    uint32_t stack_size;    // Stack size in bytes
    uint8_t  priority;      // Task priority (0 = highest)
    uint8_t  state;         // ready, running, blocked, suspended
    uint32_t timeout;       // For timed waits
    void     (*entry)(void*); // Entry function
    void     *arg;          // Entry function argument
    char     name[16];      // Human-readable name
} TCB_t;

// Priority-based scheduler (simplified)
TCB_t *scheduler_next(void) {
    TCB_t *highest = NULL;
    for (int i = 0; i < NUM_TASKS; i++) {
        if (tasks[i].state == READY) {
            if (!highest || tasks[i].priority < highest->priority) {
                highest = &tasks[i];
            }
        }
    }
    return highest;
}
```

---

## 4. Edge Computing Pattern

```
┌──────────────────────────────────────────────┐
│                  CLOUD                         │
│  ┌────────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Analytics   │  │ Model    │  │ Dashboard │ │
│  │ Pipeline    │  │ Registry │  │           │ │
│  └────────────┘  └──────────┘  └───────────┘ │
└──────────────────────┬───────────────────────┘
                       │ MQTT/HTTP
┌──────────────────────▼───────────────────────┐
│                  EDGE DEVICE                   │
│  ┌────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Ingress│─▶│ Local         │─▶│ Egress   │  │
│  │        │  │ Processing    │  │ (to cloud)│  │
│  └────────┘  │ + Filter      │  └──────────┘  │
│              │ + Aggregate   │                 │
│              │ + ML Infer    │                 │
│              └──────────────┘                  │
└──────────────────────┬───────────────────────┘
                       │ GPIO/I2C/SPI
┌──────────────────────▼───────────────────────┐
│                  DEVICE LAYER                   │
│  ┌────────┐  ┌────────┐  ┌──────────────────┐ │
│  │Sensor 1│  │Sensor 2│  │Actuator          │ │
│  │(temp)  │  │(motion)│  │(motor/valve)     │ │
│  └────────┘  └────────┘  └──────────────────┘ │
└──────────────────────────────────────────────┘
```

### Edge Processing Pattern

```python
# Edge device — local processing before cloud upload
from collections import deque
import statistics
import json

class EdgeProcessor:
    def __init__(self, window_size: int = 100, upload_interval: int = 300):
        self.buffer: deque = deque(maxlen=window_size)
        self.last_upload = 0
        self.upload_interval = upload_interval

    def process_reading(self, value: float) -> dict | None:
        """Process sensor reading — returns alert if needed."""
        self.buffer.append(value)

        if len(self.buffer) < 10:
            return None  # Need minimum samples

        # Local anomaly detection
        mean = statistics.mean(self.buffer)
        stdev = statistics.stdev(self.buffer) if len(self.buffer) > 1 else 0

        if stdev > 0 and abs(value - mean) > 3 * stdev:
            return {
                "type": "alert",
                "value": value,
                "mean": mean,
                "std": stdev,
                "timestamp": time.time(),
            }

        # Periodic upload
        if time.time() - self.last_upload > self.upload_interval:
            self.last_upload = time.time()
            return {
                "type": "telemetry",
                "mean": mean,
                "min": min(self.buffer),
                "max": max(self.buffer),
                "count": len(self.buffer),
                "timestamp": time.time(),
            }

        return None
```

---

## 5. IoT Security

| Threat | Mitigation |
|---|---|
| **Device tampering** | Secure boot, signed firmware, TPM |
| **Network eavesdropping** | TLS/DTLS, mTLS for MQTT |
| **Firmware attacks** | Signed updates, rollback protection |
| **Physical access** | Tamper seals, encrypted storage, erase on tamper |
| **Side-channel attacks** | Constant-time crypto, power analysis protection |
| **Replay attacks** | Nonces, timestamps, sequence numbers |

### Secure MQTT Connection

```python
# MQTT with TLS
import ssl

def create_secure_client(device_cert: str, device_key: str, ca_cert: str) -> IoTDeviceClient:
    client = IoTDeviceClient(
        broker_host="iot.example.com",
        broker_port=8883,  # MQTTS port
    )

    client.client.tls_set(
        ca_certs=ca_cert,
        certfile=device_cert,
        keyfile=device_key,
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLSv1_2,
    )
    return client
```

---

## Quick Reference: IoT/Embedded by Node Type

| Node Type | IoT/Embedded Mapping |
|---|---|
| **Input** | Sensor reading, GPIO input, ADC conversion, button press |
| **Logic** | Edge processing, data fusion, state machine, threshold detection |
| **Database** | Local flash storage, time-series buffers, config EEPROM |
| **UI** | LED/LCD display, mobile app dashboard, web console |
| **API** | MQTT publish/subscribe, CoAP, BLE GATT, cloud upload |

---

*For deeper IoT/Embedded concepts, see Bible level `23-iot-embedded-deep/` — BLE, LoRaWAN, MQTT, RTOS, embedded Linux, Yocto, and IoT security.*
