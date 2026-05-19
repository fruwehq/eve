# frozen_string_literal: true

require "json"
require "time"

module Eve
  module SDK
    module Log
      def self.info(message, prefix: nil, stream: $stdout)
        emit(:info, message, prefix: prefix, stream: stream)
      end

      def self.warn(message, prefix: nil, stream: $stderr)
        emit(:warn, message, prefix: prefix, stream: stream)
      end

      def self.error(message, prefix: nil, stream: $stderr)
        emit(:error, message, prefix: prefix, stream: stream)
      end

      def self.emit(level, message, prefix: nil, stream: $stdout, json: false)
        if json
          entry = {
            "level" => level.to_s,
            "message" => message,
            "timestamp" => Time.now.utc.iso8601
          }
          entry["prefix"] = prefix if prefix
          stream.puts JSON.generate(entry)
        else
          line = message
          line = "[#{prefix}] #{line}" if prefix
          stream.puts line
        end
      end

      def self.stream_output(io, prefix: nil, stream: $stdout)
        return unless io
        io.each_line do |line|
          output = prefix ? "[#{prefix}] #{line}" : line
          stream.print output
          stream.flush
        end
      end
    end
  end
end
