#ifndef JAY_PACKET_PARSER_H
#define JAY_PACKET_PARSER_H

#include "constants.h"
#include <stddef.h>
#include <stdint.h>

typedef struct {
    const uint8_t *payload;
    uint16_t       payload_len;
} packet_result_t;

/**
 * Parse one packet from buf. See packet_parser.c.
 * Returns payload_len if full packet present; 0 if need more data; (uint16_t)-1 on error.
 */
uint16_t read_packet(const uint8_t *buf, size_t len, packet_result_t *out);

unsigned packet_total_bytes(uint16_t payload_len);

#endif
