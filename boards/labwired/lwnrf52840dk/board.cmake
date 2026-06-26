# Copyright (c) 2026 Andrii Shylenko
# SPDX-License-Identifier: Apache-2.0
#
# Drive Zephyr's `run` target (and therefore stock twister's `custom` simulation
# handler, which invokes `ninja run`) through the LabWired simulator. No Zephyr or
# twister fork: declaring `custom` makes Zephyr's CMakeLists create
# `run -> run_custom`, and we implement run_custom here.

set(SUPPORTED_EMU_PLATFORMS custom)

# Repo root, three levels up from boards/labwired/lwnrf52840dk.
get_filename_component(LABWIRED_ZEPHYR_ROOT ${CMAKE_CURRENT_LIST_DIR}/../../.. ABSOLUTE)

# labwired_run.py reads the board target from the build's .config, resolves (or
# derives) the system manifest, and streams the UART console to stdout for the
# ztest/console harness to score. The binary, systems dir, and any derive options
# come from the environment ($LABWIRED_BIN, $LABWIRED_SYSTEMS_DIR, $LABWIRED_CHIP,
# $LABWIRED_CHIPS_DIR), so the same target works mapped or derived.
# ZEPHYR_BASE is forwarded so the system-derivation path can ride Zephyr's
# bundled python-devicetree when the west venv has not pip-installed it.
add_custom_target(run_custom
  COMMAND ${CMAKE_COMMAND} -E env ZEPHYR_BASE=${ZEPHYR_BASE}
    ${PYTHON_EXECUTABLE}
    ${LABWIRED_ZEPHYR_ROOT}/scripts/labwired_run.py
    --build-dir ${APPLICATION_BINARY_DIR}
    --board-map ${LABWIRED_ZEPHYR_ROOT}/boards.map
  WORKING_DIRECTORY ${APPLICATION_BINARY_DIR}
  DEPENDS ${logical_target_for_zephyr_elf}
  USES_TERMINAL
  )
