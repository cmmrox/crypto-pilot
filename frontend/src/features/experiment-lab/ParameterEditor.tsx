import type { ParameterDefinition } from "./types";

interface Props {
  definitions: ParameterDefinition[];
  values: Record<string, string>;
  pinned: string[];
  onChange: (values: Record<string, string>) => void;
  onPin?: (pinned: string[]) => void;
}

export function ParameterEditor({ definitions, values, pinned, onChange, onPin }: Props) {
  return (
    <div className="lab-parameters">
      {definitions.map((field) => (
        <div className="lab-parameter" key={field.key}>
          <label htmlFor={`parameter-${field.key}`}>
            {field.label} <small>({field.unit})</small>
          </label>
          <input
            id={`parameter-${field.key}`}
            type="number"
            min={field.minimum}
            max={field.maximum}
            step={field.step}
            value={values[field.key] ?? field.default}
            required
            onChange={(event) => onChange({ ...values, [field.key]: event.target.value })}
          />
          {onPin && (
            <label className="lab-pin">
              <input
                type="checkbox"
                checked={pinned.includes(field.key)}
                onChange={(event) =>
                  onPin(
                    event.target.checked
                      ? [...pinned, field.key]
                      : pinned.filter((key) => key !== field.key),
                  )
                }
              />{" "}
              Pin for advisor
            </label>
          )}
        </div>
      ))}
    </div>
  );
}
