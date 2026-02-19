import SwiftUI
import Charts

struct DriverCompareView: View {
    @State private var vm = CompareViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    driverPickers

                    if vm.isLoading {
                        ProgressView("Crunching telemetry...")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 40)
                    } else if let error = vm.error {
                        errorView(error)
                    } else if let data = vm.comparison {
                        comparisonContent(data)
                    } else {
                        emptyPrompt
                    }
                }
                .padding()
            }
            .background(Color(.systemBackground))
            .navigationTitle("Head to Head")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Driver Pickers

    private var driverPickers: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                driverField(text: $vm.driver1Input, placeholder: "Driver 1 (e.g. VER)")
                Text("vs")
                    .font(.system(size: 14, weight: .black))
                    .foregroundStyle(.secondary)
                driverField(text: $vm.driver2Input, placeholder: "Driver 2 (e.g. NOR)")
            }

            HStack(spacing: 12) {
                // Year picker
                Menu {
                    ForEach(2021...2026, id: \.self) { year in
                        Button(String(year)) { vm.selectedYear = year }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(String(vm.selectedYear))
                            .font(.system(size: 13, weight: .bold))
                        Image(systemName: "chevron.down")
                            .font(.system(size: 9))
                    }
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(.ultraThinMaterial, in: Capsule())
                }

                Spacer()

                Button {
                    Task { await vm.compare() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 12))
                        Text("Compare")
                            .font(.system(size: 13, weight: .bold))
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(
                        LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing),
                        in: Capsule()
                    )
                }
                .disabled(vm.driver1Input.isEmpty || vm.driver2Input.isEmpty || vm.isLoading)
                .opacity(vm.driver1Input.isEmpty || vm.driver2Input.isEmpty ? 0.5 : 1)
            }

            // Quick pick chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(CompareViewModel.popularDrivers, id: \.self) { code in
                        Button {
                            if vm.driver1Input.isEmpty {
                                vm.driver1Input = code
                            } else if vm.driver2Input.isEmpty {
                                vm.driver2Input = code
                            }
                        } label: {
                            Text(code)
                                .font(.system(size: 11, weight: .bold, design: .monospaced))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background {
                                    if vm.driver1Input == code || vm.driver2Input == code {
                                        Capsule().fill(.red.opacity(0.3))
                                    } else {
                                        Capsule().fill(.ultraThinMaterial)
                                    }
                                }
                                .foregroundStyle(
                                    vm.driver1Input == code || vm.driver2Input == code
                                        ? Color.red : Color.secondary
                                )
                        }
                    }
                }
            }
        }
    }

    private func driverField(text: Binding<String>, placeholder: String) -> some View {
        TextField(placeholder, text: text)
            .font(.system(size: 14, weight: .bold, design: .monospaced))
            .textInputAutocapitalization(.characters)
            .autocorrectionDisabled()
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Empty / Error

    private var emptyPrompt: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.2.fill")
                .font(.system(size: 36))
                .foregroundStyle(.secondary)
            Text("Select two drivers to compare")
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }

    private func errorView(_ error: String) -> some View {
        VStack(spacing: 8) {
            Text("Comparison failed")
                .font(.system(size: 14, weight: .bold))
            Text(error)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    // MARK: - Comparison Content

    @ViewBuilder
    private func comparisonContent(_ data: CompareResponse) -> some View {
        // Driver cards
        HStack(spacing: 12) {
            driverCard(data.driver1, isLeft: true)
            driverCard(data.driver2, isLeft: false)
        }

        // H2H bars
        h2hSection(data)

        // Position chart
        if !data.rounds.isEmpty {
            positionChart(data)
        }

        // Round-by-round breakdown
        roundBreakdown(data)
    }

    private func driverCard(_ driver: CompareDriver, isLeft: Bool) -> some View {
        VStack(alignment: isLeft ? .leading : .trailing, spacing: 4) {
            Text(driver.code)
                .font(.system(size: 28, weight: .black))
                .foregroundStyle(
                    LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing)
                )

            Text(driver.name)
                .font(.system(size: 12, weight: .medium))
                .lineLimit(1)

            Text(driver.team)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                statPill("P\(driver.position)", icon: "trophy")
                statPill("\(Int(driver.points)) pts", icon: "star")
                if driver.wins > 0 {
                    statPill("\(driver.wins)W", icon: "flag.checkered")
                }
            }
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, alignment: isLeft ? .leading : .trailing)
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func statPill(_ text: String, icon: String) -> some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.system(size: 8))
            Text(text)
                .font(.system(size: 10, weight: .bold))
        }
        .foregroundStyle(.secondary)
    }

    // MARK: - H2H Bars

    private func h2hSection(_ data: CompareResponse) -> some View {
        VStack(spacing: 12) {
            Text("HEAD TO HEAD")
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            h2hBar(
                label: "Qualifying",
                d1: data.qualifyingH2h.d1,
                d2: data.qualifyingH2h.d2,
                d1Code: data.driver1.code,
                d2Code: data.driver2.code
            )

            h2hBar(
                label: "Race",
                d1: data.raceH2h.d1,
                d2: data.raceH2h.d2,
                d1Code: data.driver1.code,
                d2Code: data.driver2.code
            )

            if let avg1 = data.avgRacePosition.d1, let avg2 = data.avgRacePosition.d2 {
                HStack {
                    Text("Avg Race Pos")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(String(format: "%.1f", avg1))
                        .font(.system(size: 13, weight: .black, design: .monospaced))
                        .foregroundStyle(avg1 < avg2 ? Color.green : Color.red)
                    Text("vs")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.1f", avg2))
                        .font(.system(size: 13, weight: .black, design: .monospaced))
                        .foregroundStyle(avg2 < avg1 ? Color.green : Color.red)
                }
                .padding(.horizontal, 12)
            }
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func h2hBar(label: String, d1: Int, d2: Int, d1Code: String, d2Code: String) -> some View {
        let total = max(d1 + d2, 1)
        let d1Frac = CGFloat(d1) / CGFloat(total)

        return VStack(spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(d1Code) \(d1) - \(d2) \(d2Code)")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
            }

            GeometryReader { geo in
                HStack(spacing: 2) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(LinearGradient(colors: [.red, .orange], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(geo.size.width * d1Frac, 4))

                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.secondary.opacity(0.3))
                }
            }
            .frame(height: 8)
        }
        .padding(.horizontal, 12)
    }

    // MARK: - Position Chart

    private func positionChart(_ data: CompareResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("RACE POSITIONS")
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            Chart {
                ForEach(data.rounds) { round in
                    if let pos = round.d1Race {
                        LineMark(
                            x: .value("Round", round.round),
                            y: .value("Position", pos)
                        )
                        .foregroundStyle(.red)
                        .symbol(.circle)
                        .interpolationMethod(.catmullRom)

                        PointMark(
                            x: .value("Round", round.round),
                            y: .value("Position", pos)
                        )
                        .foregroundStyle(.red)
                        .symbolSize(20)
                    }

                    if let pos = round.d2Race {
                        LineMark(
                            x: .value("Round", round.round),
                            y: .value("Position", pos)
                        )
                        .foregroundStyle(.blue)
                        .symbol(.diamond)
                        .interpolationMethod(.catmullRom)

                        PointMark(
                            x: .value("Round", round.round),
                            y: .value("Position", pos)
                        )
                        .foregroundStyle(.blue)
                        .symbolSize(20)
                    }
                }
            }
            .chartYScale(domain: .automatic(includesZero: false))
            .chartYAxis {
                AxisMarks(values: .automatic) { value in
                    AxisGridLine()
                    AxisValueLabel()
                }
            }
            .chartYScale(domain: 1...20)
            .chartForegroundStyleScale([
                data.driver1.code: Color.red,
                data.driver2.code: Color.blue,
            ])
            .frame(height: 200)

            // Legend
            HStack(spacing: 16) {
                HStack(spacing: 4) {
                    Circle().fill(.red).frame(width: 8, height: 8)
                    Text(data.driver1.code)
                        .font(.system(size: 11, weight: .bold))
                }
                HStack(spacing: 4) {
                    Circle().fill(.blue).frame(width: 8, height: 8)
                    Text(data.driver2.code)
                        .font(.system(size: 11, weight: .bold))
                }
            }
            .foregroundStyle(.secondary)
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Round Breakdown

    private func roundBreakdown(_ data: CompareResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("ROUND BY ROUND")
                .font(.system(size: 10, weight: .bold))
                .tracking(2)
                .foregroundStyle(.secondary)

            // Header
            HStack(spacing: 0) {
                Text("RD").frame(width: 24, alignment: .leading)
                Text("GP").frame(maxWidth: .infinity, alignment: .leading)
                Text("Q").frame(width: 50)
                Text("R").frame(width: 50)
            }
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)

            ForEach(data.rounds) { round in
                roundRow(round, d1Code: data.driver1.code, d2Code: data.driver2.code)
            }
        }
        .padding(12)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func roundRow(_ round: CompareRound, d1Code: String, d2Code: String) -> some View {
        HStack(spacing: 0) {
            Text(String(round.round))
                .font(.system(size: 11, weight: .bold))
                .frame(width: 24, alignment: .leading)

            Text(round.name.replacingOccurrences(of: "Grand Prix", with: "GP"))
                .font(.system(size: 11))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)

            // Qualifying
            if let q1 = round.d1Quali, let q2 = round.d2Quali {
                Text("\(q1)-\(q2)")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(q1 < q2 ? Color.green : (q1 > q2 ? Color.red : Color.secondary))
                    .frame(width: 50)
            } else {
                Text("-")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(width: 50)
            }

            // Race
            if let r1 = round.d1Race, let r2 = round.d2Race {
                Text("\(r1)-\(r2)")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(r1 < r2 ? Color.green : (r1 > r2 ? Color.red : Color.secondary))
                    .frame(width: 50)
            } else {
                Text("-")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(width: 50)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
    }
}
