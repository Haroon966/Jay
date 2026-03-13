# Dependencies: opus from idf_component.yml (esphome/micro-opus)
idf_component_register(
    SRCS
        "main.c"
        "spp_task.c"
        "audio_task.c"
        "codec.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver
        bt
        esp_spp
        nvs_flash
        freertos
        esp_log
        esphome__micro-opus
)
