interface TelemetryData {
  driver1: string;
  driver2: string;
  year: number;
  grand_prix: string;
  gap: number;
  s1: number;
  s2: number;
  s3: number;
}

interface Props {
  data: TelemetryData;
}

const TelemetryCard = ({ data }: Props) => {
  const renderDelta = (delta: number) => {
    const isFaster = delta < 0;
    const color = isFaster ? "text-green-400" : "text-red-400";
    const sign = delta > 0 ? "+" : "";
    return <span className={`font-mono font-bold ${color}`}>{sign}{delta.toFixed(3)}s</span>;
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 my-2 max-w-md shadow-lg">
      <div className="flex justify-between items-center border-b border-gray-700 pb-2 mb-3">
        <h3 className="text-gray-100 font-bold text-sm uppercase tracking-wider">
          Telemetry: {data.grand_prix} {data.year}
        </h3>
        <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">Q3 Data</span>
      </div>

      <div className="flex justify-between items-center mb-4 text-xl font-bold">
        <div className="text-blue-400">{data.driver1}</div>
        <div className="text-xs text-gray-500 font-normal">VS</div>
        <div className="text-orange-400">{data.driver2}</div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between items-center bg-gray-900/50 p-2 rounded">
          <span className="text-gray-400">Total Gap</span>
          {renderDelta(data.gap)}
        </div>
        <div className="flex justify-between items-center border-t border-gray-700 pt-2 mt-2">
          <span className="text-gray-500">Sector 1</span>
          {renderDelta(data.s1)}
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-500">Sector 2</span>
          {renderDelta(data.s2)}
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-500">Sector 3</span>
          {renderDelta(data.s3)}
        </div>
      </div>
      
      <div className="mt-3 text-xs text-center text-gray-500">
        *Negative values (Green) mean {data.driver1} was faster.
      </div>
    </div>
  );
};

export default TelemetryCard;