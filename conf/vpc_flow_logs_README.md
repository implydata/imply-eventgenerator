# AWS VPC Flow Logs Generator

## Overview

This configuration generates realistic AWS VPC Flow Log records that simulate various network traffic patterns commonly seen in production VPC environments. The generator models connection lifecycles with proper state machines, realistic IP distributions, and appropriate packet/byte counts.

The generator simulates six main traffic patterns:

1. **Web Traffic (40%)** - HTTP/HTTPS traffic from external IPs to web servers
2. **Database Traffic (25%)** - Database queries from application servers to database servers
3. **SSH Admin Sessions (10%)** - SSH administrative access to servers
4. **Internal API Calls (20%)** - Microservice-to-microservice REST API communication
5. **Port Scanning Attacks (3%)** - Malicious port scanning activity
6. **DNS Queries (2%)** - UDP DNS resolution requests

## Output fields

The generated logs conform to AWS VPC Flow Logs version 2 format:

| Field | Description | Example |
| --- | --- | --- |
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

## State machine

Each traffic pattern uses a two-state model:

```text
initial → web_traffic_init → web_traffic_data (→ continue or stop)
        → database_traffic_init → database_query (→ continue or stop)
        → ssh_traffic_init → ssh_session (→ continue or stop)
        → internal_api_init → internal_api_call (→ continue or stop)
        → port_scan_init (↻ rapid loop)
        → dns_traffic_init (↻ loop)
```

1. **Init State**: Connection establishment — sets up the connection tuple (src/dst IPs and ports), represents TCP handshake or initial packet, then transitions to the data transfer state.
2. **Data Transfer State**: Active communication — maintains the connection tuple via variable persistence, generates higher packet counts and byte volumes, and can loop to simulate multiple requests/queries on the same connection.

## Usage examples

Generate JSON output:

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -m 10 \
  -n 1000 \
  -t conf/tar/stdout.json
```

Generate in AWS VPC Flow Log format (space-separated):

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -m 10 \
  -n 1000 \
  -t conf/tar/stdout.json
```

Generate historical data:

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -s "2024-01-01T00:00:00" \
  -r PT1H \
  -m 50 \
  -t conf/tar/file.json
```

Stream to Kafka:

```bash
python3 generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -m 100 \
  -t conf/tar/kafka.json
```

## Use cases

- **Testing SIEM/Security Analytics**: Detect port scanning, unusual traffic patterns
- **Network Monitoring**: Monitor traffic volumes, connection patterns
- **Capacity Planning**: Understand typical traffic distributions
- **Log Ingestion Testing**: Test log pipeline performance with realistic VPC data
- **Training/Demos**: Generate realistic data for demonstrations
- **Development**: Test analytics queries without production data

## Additional information

### Network architecture

The configuration models a realistic VPC network with the following subnets:

- **VPC CIDR**: 10.0.0.0/16
- **Web Servers**: 10.0.0.0 - 10.0.0.4 (5 instances)
- **Application Servers**: 10.0.0.0 - 10.0.0.9 (10 instances)
- **Database Servers**: 10.0.1.0 - 10.0.1.2 (3 instances in separate subnet)
- **Microservices**: 10.0.2.0 - 10.0.2.19 (20 containers/instances)
- **External IPs**: 8.8.0.0 - 223.255.255.255 (simulating internet traffic)

The configuration includes 8 Elastic Network Interfaces (ENIs) (`eni-0a1b2c3d4e5f60001` through `eni-0a1b2c3d4e5f60008`) and simulates a multi-account setup with three account IDs.

### Traffic pattern details

#### Web Traffic

**States**: `web_traffic_init` → `web_traffic_data`

- **Protocol**: TCP (6)
- **Ports**: 80 (HTTP), 443 (HTTPS)
- **Source**: External IPs (internet clients)
- **Destination**: Web server pool (10.0.0.0-10.0.0.4)
- **Connection Setup**: 3 packets, 180-240 bytes (TCP handshake)
- **Data Transfer**: 50-500 packets, 5KB-500KB per request
- **Duration**: 1-5 seconds per request
- **Behavior**: 25% chance of multiple requests on same connection

#### Database Traffic

**States**: `database_traffic_init` → `database_query` (can loop)

- **Protocol**: TCP (6)
- **Ports**: 3306 (MySQL), 5432 (PostgreSQL), 1433 (SQL Server), 27017 (MongoDB)
- **Source**: Application servers (10.0.0.0-10.0.0.9)
- **Destination**: Database servers (10.0.1.0-10.0.1.2)
- **Connection Setup**: 3 packets, 180-240 bytes
- **Query Execution**: 10-200 packets, 1KB-100KB
- **Duration**: 0.5-3 seconds per query
- **Behavior**: 60% chance of multiple queries on same connection

#### SSH Admin Sessions

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

#### Internal API Calls

**States**: `internal_api_init` → `internal_api_call` (can loop)

- **Protocol**: TCP (6)
- **Ports**: 8080, 8081, 8443, 9090, 3000, 4000, 5000, 6000
- **Source**: Microservices subnet (10.0.2.0-10.0.2.19)
- **Destination**: Same microservices subnet (service mesh)
- **Connection**: 3-8 packets, 200-500 bytes
- **API Call**: 10-100 packets, 500B-50KB (typical JSON payloads)
- **Duration**: 0.1-1 second (fast internal network)
- **Behavior**: 20% chance of chained API calls

#### Port Scanning Attacks

**State**: `port_scan_init` (loops rapidly)

- **Protocol**: TCP (6)
- **Source**: Known attacker IPs (limited IP set for detection)
- **Destination**: Wide range of internal IPs (10.0.0.0-10.0.0.49)
- **Port Range**: Random ports from 1-65535
- **Pattern**: Single SYN packet (60 bytes) per probe
- **Action**: 75% REJECT, 25% ACCEPT (finding open ports)
- **Behavior**: Rapid scanning with exponential mean of 0.01 seconds between probes

#### DNS Traffic

**State**: `dns_traffic_init` (can loop)

- **Protocol**: UDP (17)
- **Port**: 53 (DNS)
- **Source**: All internal hosts (10.0.0.0-10.0.0.29)
- **Destination**: Internal DNS servers (10.0.0.2-10.0.0.3)
- **Packets**: 2-4 packets (query + response, sometimes retries)
- **Size**: 100-500 bytes
- **Duration**: Very fast (<1 second)
- **Behavior**: 30% chance of multiple lookups

### Detection scenarios

The generated data supports testing various security detection scenarios:

**Port Scan Detection**:

- Multiple connection attempts from same source IP
- Connections to sequential or random ports
- High percentage of REJECT actions
- Single packet connections (SYN probes)

```sql
SELECT srcaddr, COUNT(DISTINCT dstport) as ports_scanned,
       SUM(CASE WHEN action='REJECT' THEN 1 ELSE 0 END) as rejections
FROM vpc_flow_logs
WHERE packets = 1
GROUP BY srcaddr
HAVING ports_scanned > 10
```

**Unusual Database Access**:

- Database connections from unexpected sources
- Database traffic at unusual times
- Excessive query volume

**Data Exfiltration**:

- Unusually large byte transfers
- Connections to external IPs from database/app servers

### SPL analysis examples

These Splunk Processing Language (SPL) queries help analyze the generated VPC Flow Logs data.

#### Traffic Volume Analysis

**Top talkers by bytes transferred:**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| stats sum(bytes) as total_bytes by srcaddr
| sort -total_bytes
| head 10
| eval total_mb = round(total_bytes/1024/1024, 2)
| table srcaddr total_mb
```

**Traffic distribution by protocol:**

```spl
sourcetype=vpc_flow_logs
| eval protocol_name = case(protocol=6, "TCP", protocol=17, "UDP", 1=1, "Other")
| stats count as flow_count, sum(bytes) as total_bytes by protocol_name
| eval total_gb = round(total_bytes/1024/1024/1024, 3)
| table protocol_name flow_count total_gb
```

**Hourly traffic patterns:**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| bucket _time span=1h
| stats sum(bytes) as bytes_per_hour by _time
| eval gb_per_hour = round(bytes_per_hour/1024/1024/1024, 2)
| timechart span=1h sum(gb_per_hour) as GB
```

#### Security Detection

**Port scan detection:**

```spl
sourcetype=vpc_flow_logs packets=1
| stats dc(dstport) as unique_ports,
        count as connection_attempts,
        sum(eval(if(action="REJECT",1,0))) as rejections
        by srcaddr
| where unique_ports > 10
| eval reject_rate = round(rejections/connection_attempts*100, 1)
| sort -unique_ports
| table srcaddr unique_ports connection_attempts rejections reject_rate
```

**Failed connection attempts:**

```spl
sourcetype=vpc_flow_logs action=REJECT
| stats count as reject_count by srcaddr, dstaddr, dstport
| sort -reject_count
| head 20
| table srcaddr dstaddr dstport reject_count
```

**Connections from unexpected sources to databases:**

```spl
sourcetype=vpc_flow_logs dstport IN (3306, 5432, 1433, 27017) action=ACCEPT
| where NOT match(srcaddr, "^10\.0\.0\.")
| stats count as suspicious_connections,
        sum(bytes) as total_bytes,
        values(dstport) as db_ports
        by srcaddr, dstaddr
| eval total_mb = round(total_bytes/1024/1024, 2)
| table srcaddr dstaddr db_ports suspicious_connections total_mb
```

#### Network Performance

**Average connection duration by service:**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| eval duration = end - start
| eval service = case(
    dstport=443 OR dstport=80, "Web",
    dstport IN (3306,5432,1433,27017), "Database",
    dstport=22, "SSH",
    dstport IN (8080,8081,8443,9090), "API",
    dstport=53, "DNS",
    1=1, "Other")
| stats avg(duration) as avg_duration_sec,
        median(duration) as median_duration_sec,
        count as flow_count
        by service
| eval avg_duration_sec = round(avg_duration_sec, 2)
| eval median_duration_sec = round(median_duration_sec, 2)
| table service flow_count avg_duration_sec median_duration_sec
```

**Connection success rate by destination port:**

```spl
sourcetype=vpc_flow_logs
| stats count as total,
        sum(eval(if(action="ACCEPT",1,0))) as accepted,
        sum(eval(if(action="REJECT",1,0))) as rejected
        by dstport
| eval success_rate = round(accepted/total*100, 1)
| where total > 5
| sort -total
| head 20
| table dstport total accepted rejected success_rate
```

**Packets per flow analysis:**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| stats avg(packets) as avg_packets,
        median(packets) as median_packets,
        max(packets) as max_packets,
        count as flows
        by dstport
| where flows > 10
| eval avg_packets = round(avg_packets, 0)
| sort -avg_packets
| head 15
| table dstport flows avg_packets median_packets max_packets
```

#### Traffic Pattern Analysis

**Web traffic patterns (HTTP/HTTPS):**

```spl
sourcetype=vpc_flow_logs dstport IN (80, 443) action=ACCEPT
| eval web_service = if(dstport=443, "HTTPS", "HTTP")
| stats count as requests,
        avg(bytes) as avg_bytes,
        avg(packets) as avg_packets,
        sum(bytes) as total_bytes
        by web_service
| eval avg_kb = round(avg_bytes/1024, 1)
| eval total_gb = round(total_bytes/1024/1024/1024, 2)
| table web_service requests avg_kb avg_packets total_gb
```

**Database query patterns:**

```spl
sourcetype=vpc_flow_logs dstport IN (3306, 5432, 1433, 27017) action=ACCEPT
| eval db_type = case(
    dstport=3306, "MySQL",
    dstport=5432, "PostgreSQL",
    dstport=1433, "SQL Server",
    dstport=27017, "MongoDB")
| eval duration = end - start
| stats count as queries,
        avg(duration) as avg_duration,
        avg(bytes) as avg_bytes,
        sum(bytes) as total_bytes
        by db_type, dstaddr
| eval avg_duration = round(avg_duration, 2)
| eval avg_kb = round(avg_bytes/1024, 1)
| eval total_mb = round(total_bytes/1024/1024, 1)
| table db_type dstaddr queries avg_duration avg_kb total_mb
```

**SSH session analysis:**

```spl
sourcetype=vpc_flow_logs dstport=22 action=ACCEPT
| eval duration = end - start
| stats count as sessions,
        avg(duration) as avg_duration,
        sum(duration) as total_duration,
        avg(bytes) as avg_bytes,
        dc(srcaddr) as unique_sources
        by dstaddr
| eval avg_duration_min = round(avg_duration/60, 1)
| eval total_duration_hours = round(total_duration/3600, 2)
| eval avg_kb = round(avg_bytes/1024, 1)
| table dstaddr sessions unique_sources avg_duration_min total_duration_hours avg_kb
```

#### ENI and Account Analysis

**Traffic distribution by ENI:**

```spl
sourcetype=vpc_flow_logs
| stats count as flows,
        sum(bytes) as total_bytes,
        dc(srcaddr) as unique_sources,
        dc(dstaddr) as unique_destinations
        by interface_id
| eval total_gb = round(total_bytes/1024/1024/1024, 2)
| sort -total_gb
| table interface_id flows total_gb unique_sources unique_destinations
```

**Cross-account traffic:**

```spl
sourcetype=vpc_flow_logs
| stats count as flows,
        sum(bytes) as total_bytes,
        dc(interface_id) as unique_enis
        by account_id
| eval total_gb = round(total_bytes/1024/1024/1024, 2)
| table account_id flows total_gb unique_enis
```

#### Advanced Security Analytics

**Anomalous data transfer (potential exfiltration):**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| where NOT match(dstaddr, "^10\.")
| stats sum(bytes) as bytes_out, count as connections by srcaddr, dstaddr
| where bytes_out > 100000000
| eval mb_out = round(bytes_out/1024/1024, 1)
| sort -mb_out
| table srcaddr dstaddr connections mb_out
```

**Lateral movement detection (unusual internal connections):**

```spl
sourcetype=vpc_flow_logs
| where match(srcaddr, "^10\.") AND match(dstaddr, "^10\.")
| eval src_subnet = replace(srcaddr, "^(10\.\d+)\.\d+\.\d+", "\1")
| eval dst_subnet = replace(dstaddr, "^(10\.\d+)\.\d+\.\d+", "\1")
| where src_subnet != dst_subnet
| stats count as cross_subnet_connections,
        dc(dstaddr) as unique_destinations,
        dc(dstport) as unique_ports,
        sum(bytes) as total_bytes
        by srcaddr, src_subnet, dst_subnet
| eval total_mb = round(total_bytes/1024/1024, 1)
| sort -cross_subnet_connections
| table srcaddr src_subnet dst_subnet cross_subnet_connections unique_destinations unique_ports total_mb
```

**Connection baseline and anomaly detection:**

```spl
sourcetype=vpc_flow_logs action=ACCEPT
| eval hour = strftime(_time, "%H")
| eval is_business_hours = if(hour >= 8 AND hour <= 18, "business", "after_hours")
| stats count as connections,
        avg(bytes) as avg_bytes,
        avg(packets) as avg_packets
        by dstport, is_business_hours
| eval avg_kb = round(avg_bytes/1024, 1)
| table dstport is_business_hours connections avg_kb avg_packets
| sort dstport is_business_hours
```

### Customization

To modify the configuration:

1. **Adjust Traffic Mix**: Change probabilities in `initial` state transitions
2. **Add Traffic Patterns**: Create new state chains with appropriate variables
3. **Modify IP Ranges**: Adjust distribution min/max values for IP addresses
4. **Change Port Distributions**: Update enum values for destination ports
5. **Adjust Timing**: Modify delay distributions for different connection durations

### Technical notes

- Uses exponential distribution for realistic inter-arrival times
- Maintains connection state across state transitions using variables
- Clock type automatically tracks timing (start/end timestamps)
- Empty `{}` records from routing state can be filtered in post-processing
- Packet counts and byte sizes are correlated (more packets = more bytes)
- TCP handshake modeled with 3 packets in init states

### Implementation patterns

This configuration demonstrates several advanced patterns:

- **Variable Persistence**: Common variables (`account_id`, `interface_id`, `action`) defined once in initial state, persist through all traffic patterns
- **Start/Activity/Emit Pattern**: TCP connection lifecycle modeled with separate setup, activity (delay), and emit states for realistic flow duration
- **Multiple Records Per Connection**: Long-running connections (SSH, database) use continue loops to emit multiple flow records for same 5-tuple
- **TCP Lifecycle Pattern**: Models SYN (handshake), data transfer, and FIN phases with realistic packet/byte counts
- **Optional Emitters**: Initial routing state has no emitter field, as it only routes to traffic patterns without emitting records

For detailed explanations of these patterns, see [Common Patterns](../docs/patterns.md) and [Best Practices](../docs/best-practices.md).

### AWS documentation

- [AWS VPC Flow Logs Documentation](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [Flow Log Record Format](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html#flow-log-records)
