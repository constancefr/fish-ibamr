cmake_minimum_required(VERSION 3.15)

project(NACA0020 LANGUAGES C CXX)

find_package(IBAMR REQUIRED)

add_executable(main2d example.cpp)

target_link_libraries(main2d PRIVATE IBAMR::IBAMR2d)