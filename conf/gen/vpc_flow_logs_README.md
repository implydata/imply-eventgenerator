# AWS VPC Flow Logs Generator Configuration

## Overview

This configuration generates realistic AWS VPC Flow Log records that simulate various network traffic patterns commonly seen in production VPC environments. The generator models connection lifecycles with proper state machines, realistic IP distributions, and appropriate packet/byte counts.

## Traffic Patterns

The generator simulates six main traffic patterns with the following distribution:

1. **Web Traffic (40%)** - HTTP/HTTPS traffic from external IPs to web servers
2. **Database Traffic (25%)** - Database queries from application servers to database servers
3. **SSH Admin Sessions (10%)** - SSH administrative access to servers
4. **Internal API Calls (20%)** - Microservice-to-microservice REST API communication
5. **Port Scanning Attacks (3%)** - Malicious port scanning activity
6. **DNS Queries (2%)** - UDP DNS resolution requests

## Network Architecture

### IP Address Ranges

The configuration models a realistic VPC network with the following subnets:

- **VPC CIDR**: 10.0.0.0/16
- **Web Servers**: 10.0.0.0 - 10.0.0.4 (5 instances)
- **Application Servers**: 10.0.0.0 - 10.0.0.9 (10 instances)
- **Database Servers**: 10.0.1.0 - 10.0.1.2 (3 instances in separate subnet)
- **Microservices**: 10.0.2.0 - 10.0.2.19 (20 containers/instances)
- **External IPs**: 8.8.0.0 - 223.255.255.255 (simulating internet traffic)

### Network Interfaces

The configuration includes 8 Elastic Network Interfaces (ENIs) distributed across different instances:

- `eni-0a1b2c3d4e5f60001` through `eni-0a1b2c3d4e5f60008`

### AWS Accounts

Simulates a multi-account setup with three account IDs:

- `123456789012`
- `123456789013`
- `123456789014`

## Traffic Pattern Details

### 1. Web Traffic

**States**: `web_traffic_init` → `web_traffic_data`

- **Protocol**: TCP (6)
- **Ports**: 80 (HTTP), 443 (HTTPS)
- **Source**: External IPs (internet clients)
- **Destination**: Web server pool (10.0.0.0-10.0.0.4)
- **Connection Setup**: 3 packets, 180-240 bytes (TCP handshake)
- **Data Transfer**: 50-500 packets, 5KB-500KB per request
- **Duration**: 1-5 seconds per request
- **Behavior**: 25% chance of multiple requests on same connection

### 2. Database Traffic

**States**: `database_traffic_init` → `database_query` (can loop)

- **Protocol**: TCP (6)
- **Ports**:
  - 3306 (MySQL)
  - 5432 (PostgreSQL)
  - 1433 (SQL Server)
  - 27017 (MongoDB)
- **Source**: Application servers (10.0.0.0-10.0.0.9)
- **Destination**: Database servers (10.0.1.0-10.0.1.2)
- **Connection Setup**: 3 packets, 180-240 bytes
- **Query Execution**: 10-200 packets, 1KB-100KB
- **Duration**: 0.5-3 seconds per query
- **Behavior**: 60% chance of multiple queries on same connection

### 3. SSH Admin Sessions

**States**: `ssh_traffic_init` → `ssh_session` (can loop)

- **Protocol**: TCP (6)
- **Port**: 22 (SSH)
- **Source**: Corporate/VPN IPs (8.8.0.0-11.0.0.255 range)
- **Destination**: Internal servers (10.0.0.0-10.0.0.14)
- **Handshake**: 5-15 packets, 500-2000 bytes
- **Session Data**: 100-2000 packets, 10KB-200KB
- **Duration**: 5-30 seconds per session interval
- **Actions**: Mix of ACCEPT and REJECT (some blocked by security groups)
- **Behavior**: 40% chance of session continuing (long-lived connections)

### 4. Internal API Calls

**States**: `internal_api_init` → `internal_api_call` (can loop)

- **Protocol**: TCP (6)
- **Ports**: 8080, 8081, 8443, 9090, 3000, 4000, 5000, 6000
- **Source**: Microservices subnet (10.0.2.0-10.0.2.19)
- **Destination**: Same microservices subnet (service mesh)
- **Connection**: 3-8 packets, 200-500 bytes
- **API Call**: 10-100 packets, 500B-50KB (typical JSON payloads)
- **Duration**: 0.1-1 second (fast internal network)
- **Behavior**: 20% chance of chained API calls

### 5. Port Scanning Attacks

**State**: `port_scan_init` (loops rapidly)

- **Protocol**: TCP (6)
- **Source**: Known attacker IPs (limited IP set for detection)
- **Destination**: Wide range of internal IPs (10.0.0.0-10.0.0.49)
- **Port Range**: Random ports from 1-65535
- **Pattern**: Single SYN packet (60 bytes) per probe
- **Action**: 75% REJECT, 25% ACCEPT (finding open ports)
- **Behavior**: Rapid scanning with exponential mean of 0.01 seconds between probes

### 6. DNS Traffic

**State**: `dns_traffic_init` (can loop)

- **Protocol**: UDP (17)
- **Port**: 53 (DNS)
- **Source**: All internal hosts (10.0.0.0-10.0.0.29)
- **Destination**: Internal DNS servers (10.0.0.2-10.0.0.3)
- **Packets**: 2-4 packets (query + response, sometimes retries)
- **Size**: 100-500 bytes
- **Duration**: Very fast (<1 second)
- **Behavior**: 30% chance of multiple lookups

## State Machine Design

Each traffic pattern uses a two-state model:

1. **Init State**: Connection establishment
   - Sets up connection tuple (src/dst IPs and ports)
   - Represents TCP handshake or initial packet
   - Low packet counts and byte sizes
   - Quick transition to data transfer state

2. **Data Transfer State**: Active communication
   - Maintains connection tuple (variables preserved across states)
   - Higher packet counts and byte volumes
   - Variable duration based on traffic type
   - Can loop to simulate multiple requests/queries on same connection

## VPC Flow Log Fields

The generated logs conform to AWS VPC Flow Logs version 2 format:

| Field | Description | Example |
| ------- | ------------- | --------- |
| `version` | Flow log version | 2 |
| `account_id` | AWS account ID | 123456789012 |
| `interface_id` | ENI ID | eni-0a1b2c3d4e5f60001 |
| `srcaddr` | Source IP address | 192.168.1.5 |
| `dstaddr` | Destination IP address | 10.0.0.4 |
| `srcport` | Source port | 52341 |
| `dstport` | Destination port | 443 |
| `protocol` | IANA protocol number | 6 (TCP), 17 (UDP) |
| `packets` | Number of packets | 245 |
| `bytes` | Number of bytes | 123456 |
| `start` | Start time (Unix epoch) | 1704067200 |
| `end` | End time (Unix epoch) | 1704067205 |
| `action` | Traffic accept/reject | ACCEPT or REJECT |
| `log_status` | Logging status | OK |

## Usage Examples

### Generate JSON Output

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -m 10 \
  -n 1000 \
  -t conf/tar/stdout.json
```

### Generate AWS VPC Flow Log Format (Space-Separated)

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -m 10 \
  -n 1000 \
  -t conf/tar/stdout.json
```

### Generate Historical Data

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -s "2024-01-01T00:00:00" \
  -r PT1H \
  -m 50 \
  -t conf/tar/file.json
```

This generates one hour of flow logs starting from January 1, 2024.

### Stream to Kafka

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -m 100 \
  -t conf/tar/kafka.json
```

## Use Cases

This generator is ideal for:

1. **Testing SIEM/Security Analytics**: Detect port scanning, unusual traffic patterns
2. **Network Monitoring**: Monitor traffic volumes, connection patterns
3. **Capacity Planning**: Understand typical traffic distributions
4. **Log Ingestion Testing**: Test log pipeline performance with realistic VPC data
5. **Training/Demos**: Generate realistic data for demonstrations
6. **Development**: Test analytics queries without production data

## Detection Scenarios

The generated data supports testing various security detection scenarios:

### Port Scan Detection

- Multiple connection attempts from same source IP
- Connections to sequential or random ports
- High percentage of REJECT actions
- Single packet connections (SYN probes)

### Example Query

```sql
SELECT srcaddr, COUNT(DISTINCT dstport) as ports_scanned,
       SUM(CASE WHEN action='REJECT' THEN 1 ELSE 0 END) as rejections
FROM vpc_flow_logs
WHERE packets = 1
GROUP BY srcaddr
HAVING ports_scanned > 10
```

### Unusual Database Access

- Database connections from unexpected sources
- Database traffic at unusual times
- Excessive query volume

### Data Exfiltration

- Unusually large byte transfers
- Connections to external IPs from database/app servers

## Customization

To modify the configuration:

1. **Adjust Traffic Mix**: Change probabilities in `initial` state transitions
2. **Add Traffic Patterns**: Create new state chains with appropriate variables
3. **Modify IP Ranges**: Adjust distribution min/max values for IP addresses
4. **Change Port Distributions**: Update enum values for destination ports
5. **Adjust Timing**: Modify delay distributions for different connection durations

## Technical Notes

- Uses exponential distribution for realistic inter-arrival times
- Maintains connection state across state transitions using variables
- Clock type automatically tracks timing (start/end timestamps)
- Empty `{}` records from routing state can be filtered in post-processing
- Packet counts and byte sizes are correlated (more packets = more bytes)
- TCP handshake modeled with 3 packets in init states

## Related Files

- **Generator Config**: `conf/gen/vpc_flow_logs.json`
- **Format Template**: `conf/form/vpc_flow_logs.txt`
- **This README**: `conf/gen/vpc_flow_logs_README.md`

## Implementation Patterns

This configuration demonstrates several advanced patterns documented in the Event Generator documentation:

- **Variable Persistence**: Common variables (`account_id`, `interface_id`, `action`) defined once in initial state, persist through all traffic patterns
- **Start→Activity→Emit Pattern**: TCP connection lifecycle modeled with separate setup, activity (delay), and emit states for realistic flow duration
- **Multiple Records Per Connection**: Long-running connections (SSH, database) use continue loops to emit multiple flow records for same 5-tuple
- **TCP Lifecycle Pattern**: Models SYN (handshake), data transfer, and FIN phases with realistic packet/byte counts
- **Optional Emitters**: Initial routing state has no emitter field, as it only routes to traffic patterns without emitting records

For detailed explanations of these patterns, see:

- [Common Patterns](../../docs/patterns.md)
- [Best Practices](../../docs/best-practices.md)

## AWS Documentation

For more information on VPC Flow Logs:

- [AWS VPC Flow Logs Documentation](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [Flow Log Record Format](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html#flow-log-records)
