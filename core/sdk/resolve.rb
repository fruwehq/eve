# frozen_string_literal: true

require "json"

module Egame
  module SDK
    class SchemaValidationError < StandardError; end

    class ResolvedInstance
      attr_reader :raw

      def self.schema_dir
        File.join(File.expand_path("../schema", __dir__))
      end

      def self.schema_path
        File.join(schema_dir, "resolved-instance.schema.json")
      end

      def self.load_schemer
        require "json_schemer"
        schema = JSON.parse(File.read(schema_path))
        JSONSchemer.schema(schema)
      rescue Errno::ENOENT
        raise SchemaValidationError, "Schema file not found: #{schema_path}"
      end

      def initialize(raw)
        @raw = raw.freeze
      end

      def instance_name
        @raw.fetch("instance").fetch("name")
      end

      def provider
        @raw.fetch("machine").fetch("provider")
      end

      def engine
        @raw.fetch("engine")
      end

      def machine
        @raw.fetch("machine")
      end

      def machine_kind
        machine.fetch("kind")
      end

      def os
        @raw.fetch("os")
      end

      def os_family
        os.fetch("family")
      end

      def init
        @raw.fetch("init")
      end

      def location
        @raw.fetch("location")
      end

      def provider_config
        @raw.fetch("provider_config", {})
      end

      def bundle_packages
        @raw.fetch("bundle_packages", [])
      end

      def package_sources
        @raw.fetch("package_sources", {})
      end

      def provider_plugin
        @raw.fetch("provider_plugin")
      end

      def package_plugins
        @raw.fetch("package_plugins", [])
      end

      def stack_tags
        @raw.fetch("stack_tags")
      end

      def composition
        @raw.fetch("composition")
      end

      def to_json(*args)
        @raw.to_json(*args)
      end

      def [](key)
        @raw[key]
      end
    end

    module Resolve
      def self.from_env
        json_source = ENV["EGAME_RESOLVED_JSON"]
        raw = if json_source
                begin
                  JSON.parse(json_source)
                rescue JSON::ParserError => e
                  raise SchemaValidationError, "Invalid JSON in EGAME_RESOLVED_JSON: #{e.message}"
                end
              else
                begin
                  JSON.parse($stdin.read)
                rescue JSON::ParserError => e
                  raise SchemaValidationError, "Invalid JSON on stdin: #{e.message}"
                end
              end
        from_hash(raw)
      end

      def self.from_hash(raw)
        validate!(raw)
        ResolvedInstance.new(raw)
      end

      def self.validate!(raw)
        schemer = ResolvedInstance.load_schemer

        errors = schemer.validate(raw).to_a
        return if errors.empty?

        lines = ["Resolved instance JSON failed schema validation:"]
        errors.each do |err|
          ptr = err["data_pointer"]
          detail = err["error"] || err["type"].to_s
          lines << "  #{ptr.empty? ? "/" : ptr}: #{detail}"
        end
        raise SchemaValidationError, lines.join("\n")
      end
    end
  end
end
