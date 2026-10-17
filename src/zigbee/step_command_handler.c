#include <stdint.h>
#include <stdlib.h>
#include "step_command_handler.h"
#include "hal/tasks.h"
#include "hal/timer.h"
#include "hal/printf_selector.h"
#include "consts.h"

#define STEP_MIN_INTERVAL_MS    100

static void _trigger_callback(step_command_handler_t *self);
static void _on_step(step_command_handler_t *self, int delta);

static void _flush_handler(void *arg) {
    _trigger_callback((step_command_handler_t *)arg);
}

// Constructor
void new_step_command_handler(step_command_handler_t *self) {
    self->_scheduled_change       = 0;
    self->_last_command_sent_time = 0;
    self->_flush_task.handler     = _flush_handler;
    self->_flush_task.arg         = self;
    hal_tasks_init(&self->_flush_task);
}

// Public Functions
void step_command_handler_step_up(step_command_handler_t *self) {
    _on_step(self, 13);
}

void step_command_handler_step_down(step_command_handler_t *self) {
    _on_step(self, -13);
}

void step_command_handler_register_callback(step_command_handler_t *self,
                                            step_command_handler_callback_t callback,
                                            void *callback_arg) {
    self->_callback     = callback;
    self->_callback_arg = callback_arg;
}

// Private Functions
static void _on_step(step_command_handler_t *self, int delta) {
    self->_scheduled_change += delta;

    uint32_t now = hal_millis();

    // If current millis is less then the last command send time, then millis has rolled over.
    if (self->_last_command_sent_time > now) {
        self->_last_command_sent_time = now - STEP_MIN_INTERVAL_MS;
    }

    uint32_t elapsed = now - self->_last_command_sent_time;
    if (elapsed >= STEP_MIN_INTERVAL_MS) {
        _trigger_callback(self);
    } else {
        // Rate limited: send the accumulated steps when the window ends
        hal_tasks_schedule(&self->_flush_task, STEP_MIN_INTERVAL_MS - elapsed);
    }
}

static void _trigger_callback(step_command_handler_t *self) {
    hal_tasks_unschedule(&self->_flush_task);

    if (self->_scheduled_change == 0) {
        return;
    }

    printf("Sending command, to change by %d in %d*0.1sec\r\n", self->_scheduled_change, 1);

    self->_callback(self->_callback_arg, self->_scheduled_change, 1);

    self->_last_command_sent_time = hal_millis();
    self->_scheduled_change       = 0;
}
