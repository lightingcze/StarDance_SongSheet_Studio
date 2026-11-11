cmake_minimum_required(VERSION 3.24)
project(stardance_muscriptor_host LANGUAGES C CXX)

include(FetchContent)

# Pin the upstream implementation used by this adapter. Updating this value
# requires a fresh build and a review of the upstream API and licence notices.
FetchContent_Declare(muscriptor_source
  URL https://github.com/DamRsn/muscriptor.cpp/archive/8589219cc3b584bce970f95aec2ec4a04e53b280.zip
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  SOURCE_SUBDIR cpp
)
set(MUSCRIPTOR_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MUSCRIPTOR_BUILD_BENCH OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(muscriptor_source)

add_executable(muscriptor_cli muscriptor_cli.cpp)
target_link_libraries(muscriptor_cli PRIVATE muscriptor_ggml)
target_compile_features(muscriptor_cli PRIVATE cxx_std_23)
set_target_properties(muscriptor_cli PROPERTIES CXX_EXTENSIONS OFF)
set_target_properties(muscriptor_cli PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
