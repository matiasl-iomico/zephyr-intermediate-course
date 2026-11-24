# Course test for l2-task1: runs the student's app/src/counter.c from two threads.
# CI takes this folder from the course repository; don't change it.
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(l2_counter_test)

target_sources(app PRIVATE
    src/test_counter.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../app/src/counter.c
)
target_include_directories(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../app/src)
