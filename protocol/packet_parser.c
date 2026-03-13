/**
 * Jay – Packet parser for SPP stream
 * Reads 2-byte little-endian length + N-byte payload. Reusable in firmware and desktop.
 */
#include "packet_parser.h"
#include <stddef.h>
#include <stdint.h>

/**
 * Parse one packet from buf. Expects at least 2 bytes for length.
 * If buf has 2 + N bytes (N = length), returns payload pointer and length.
 * payload points into buf at offset 2; caller must not write to buf until done with payload.
 *
 * Returns: payload_len if a full packet is present (2 + N bytes available);
 *          0 if more data needed;
 *          (uint16_t)-1 on error (e.g. N > MAX_PAYLOAD_LEN).
 */
uint16_t read_packet(const uint8_t *buf, size_t len, packet_result_t *out)
{
    if (buf == NULL || out == NULL || len < PACKET_HEADER_SIZE)
        return 0;

    uint16_t n = (uint16_t)buf[0] | ((uint16_t)buf[1] << 8);
    if (n > MAX_PAYLOAD_LEN)
        return (uint16_t)-1;
    if (len < PACKET_HEADER_SIZE + n)
        return 0;

    out->payload     = buf + PACKET_HEADER_SIZE;
    out->payload_len = n;
    return n;
}

/**
 * Total bytes consumed for a packet with payload length N.
 */
unsigned packet_total_bytes(uint16_t payload_len)
{
    return PACKET_HEADER_SIZE + payload_len;
}
