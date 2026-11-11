#include "muscriptor/muscriptor.hpp"

#include <atomic>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic_bool cancelled{false};

std::string escape_json(std::string_view input) {
    std::string result;
    result.reserve(input.size() + 8);
    for (const unsigned char c : input) {
        switch (c) {
            case '"': result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\b': result += "\\b"; break;
            case '\f': result += "\\f"; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default:
                if (c < 0x20) {
                    constexpr char hex[] = "0123456789abcdef";
                    result += "\\u00";
                    result += hex[(c >> 4) & 0xf];
                    result += hex[c & 0xf];
                } else {
                    result += static_cast<char>(c);
                }
        }
    }
    return result;
}

std::string note_json(const msl::Note& note) {
    const auto instrument = msl::instrumentLabel(note.program);
    return "{\"onset\":" + std::to_string(note.onset) +
        ",\"offset\":" + std::to_string(note.offset) +
        ",\"pitch\":" + std::to_string(note.pitch) +
        ",\"program\":" + std::to_string(note.program) +
        ",\"instrument\":\"" + escape_json(instrument) +
        "\",\"is_drum\":" + (note.is_drum ? "true}" : "false}");
}

void print_notes(const std::span<const msl::Note> notes) {
    std::cout << "[";
    for (std::size_t i = 0; i < notes.size(); ++i) {
        if (i) std::cout << ",";
        std::cout << note_json(notes[i]);
    }
    std::cout << "]";
}

std::string arg_value(int argc, char** argv, const std::string& name, bool required = true) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (argv[i] == name) return argv[i + 1];
    }
    if (required) throw std::runtime_error("Missing required argument: " + name);
    return {};
}

} // namespace

int main(int argc, char** argv) {
    try {
        const std::filesystem::path weights = arg_value(argc, argv, "--weights");
        const std::filesystem::path input = arg_value(argc, argv, "--input-f32");
        const std::filesystem::path cancel_file = arg_value(argc, argv, "--cancel-file", false);
        std::string resume = arg_value(argc, argv, "--resume", false);
        const std::string resume_file = arg_value(argc, argv, "--resume-file", false);
        if (!resume_file.empty()) {
            std::ifstream saved_resume(resume_file, std::ios::binary);
            if (saved_resume) resume.assign(std::istreambuf_iterator<char>(saved_resume), std::istreambuf_iterator<char>());
        }
        int threads = 0;
        const std::string thread_arg = arg_value(argc, argv, "--threads", false);
        if (!thread_arg.empty()) threads = std::max(1, std::stoi(thread_arg));

        std::jthread cancel_watcher;
        if (!cancel_file.empty()) {
            cancel_watcher = std::jthread([cancel_file](std::stop_token stop) {
                while (!stop.stop_requested()) {
                    std::error_code error;
                    if (std::filesystem::exists(cancel_file, error)) {
                        cancelled.store(true, std::memory_order_relaxed);
                        return;
                    }
                    std::this_thread::sleep_for(std::chrono::milliseconds(80));
                }
            });
        }

        msl::LoadOptions load_options;
        load_options.should_cancel = [] { return cancelled.load(std::memory_order_relaxed); };
        load_options.on_progress = [](const float progress) {
            std::cout << "{\"type\":\"loading\",\"progress\":" << progress << "}\n" << std::flush;
        };
        auto loaded = msl::Transcriber::load(weights, load_options);
        if (!loaded) {
            const bool was_cancelled = cancelled.load(std::memory_order_relaxed) || loaded.error() == msl::Error::Cancelled;
            std::cout << "{\"type\":\"" << (was_cancelled ? "cancelled" : "error")
                      << "\",\"message\":\"" << escape_json(msl::describe(loaded.error())) << "\"}\n" << std::flush;
            return was_cancelled ? 3 : 2;
        }
        auto transcriber = std::move(*loaded);

        std::ifstream source(input, std::ios::binary);
        if (!source) throw std::runtime_error("Cannot open float32 audio input.");
        std::vector<float> samples;
        source.seekg(0, std::ios::end);
        const auto bytes = source.tellg();
        if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(float)) != 0)
            throw std::runtime_error("Audio input is not raw float32 data.");
        samples.resize(static_cast<std::size_t>(bytes / sizeof(float)));
        source.seekg(0, std::ios::beg);
        if (!samples.empty()) source.read(reinterpret_cast<char*>(samples.data()), bytes);
        if (!source && !samples.empty()) throw std::runtime_error("Could not read complete audio input.");

        msl::TranscribeOptions options;
        options.n_threads = threads;
        options.resume_from = resume;
        options.should_cancel = [] { return cancelled.load(std::memory_order_relaxed); };
        const std::string backend(transcriber.device().backend);
        const std::string device(transcriber.device().name);
        auto result = transcriber.transcribe(samples, options, [](const msl::TranscriptionUpdate& update) {
            std::cout << "{\"type\":\"chunk\",\"progress\":" << update.progress
                      << ",\"finalized_through\":" << update.finalized_through
                      << ",\"resume_point\":\"" << escape_json(update.resume_point) << "\",\"notes\":";
            print_notes(update.new_notes);
            std::cout << "}\n" << std::flush;
            return !cancelled.load(std::memory_order_relaxed);
        });
        if (!result) {
            const bool was_cancelled = cancelled.load(std::memory_order_relaxed) || result.error() == msl::Error::Cancelled;
            std::cout << "{\"type\":\"" << (was_cancelled ? "cancelled" : "error") << "\",\"message\":\""
                      << escape_json(msl::describe(result.error())) << "\"}\n" << std::flush;
            return was_cancelled ? 3 : 2;
        }
        std::cout << "{\"type\":\"done\",\"duration\":"
                  << static_cast<double>(samples.size()) / msl::Transcriber::SAMPLE_RATE
                  << ",\"backend\":\"" << escape_json(backend)
                  << "\",\"device\":\"" << escape_json(device)
                  << "\",\"note_count\":" << result->size() << "}\n" << std::flush;
        return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"type\":\"error\",\"message\":\"" << escape_json(error.what()) << "\"}\n" << std::flush;
        return 2;
    }
}
