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
        nvs_flash
        freertos
        log
        esphome__micro-opus
)
