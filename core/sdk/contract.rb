# frozen_string_literal: true

require "json"

module Eve
  module SDK
    class ContractError < StandardError; end

    module Contract
      def self.schema_path
        File.join(File.expand_path("../schema", __dir__), "command-io.schema.json")
      end

      def self.load_raw_schema
        JSON.parse(File.read(schema_path))
      rescue Errno::ENOENT
        raise ContractError, "Schema file not found: #{schema_path}"
      end

      def self.load_schemer
        require "json_schemer"
        JSONSchemer.schema(load_raw_schema)
      end

      def self.validate_output!(data, def_name: nil)
        if def_name
          resolved = resolve_def(def_name)
          validate_with!(resolved, data, "command output")
        else
          true
        end
      end

      def self.validate_input!(data)
        path = File.join(File.expand_path("../schema", __dir__), "resolved-instance.schema.json")
        require "json_schemer"
        schema = begin
          JSON.parse(File.read(path))
        rescue Errno::ENOENT
          raise ContractError, "Schema file not found: #{path}"
        end
        resolved_schemer = JSONSchemer.schema(schema)
        validate_with!(resolved_schemer, data, "command input")
      end

      def self.validate_with!(schemer, data, label)
        errors = schemer.validate(data).to_a
        return true if errors.empty?

        lines = ["#{label} failed schema validation:"]
        errors.each do |err|
          ptr = err["data_pointer"]
          detail = err["error"] || err["type"].to_s
          lines << "  #{ptr.empty? ? "/" : ptr}: #{detail}"
        end
        raise ContractError, lines.join("\n")
      end

      def self.resolve_def(def_name)
        raw = load_raw_schema
        defs = raw["$defs"] || raw["defs"] || {}
        defn = defs.fetch(def_name) do
          raise ContractError, "Unknown $defs entry: #{def_name}"
        end
        require "json_schemer"
        JSONSchemer.schema(defn)
      end
    end
  end
end
