import SwiftUI

/// Protocol for ad integration. Swap the stub with AdMob/AppLovin later.
protocol AdProvider {
    func loadBanner() -> AnyView
    func loadNativeAd() -> AnyView
    func showInterstitial()
    var isPremium: Bool { get }
}

/// Stub implementation — returns empty views, no ads shown.
@Observable
final class StubAdManager: AdProvider {
    var isPremium: Bool {
        UserDefaults.standard.bool(forKey: "isPremiumUser")
    }

    func loadBanner() -> AnyView {
        AnyView(EmptyView())
    }

    func loadNativeAd() -> AnyView {
        AnyView(EmptyView())
    }

    func showInterstitial() {
        // No-op until real ad SDK is integrated
    }
}

/// Designated ad placement zones.
/// Insert these views where ads should appear. They respect the premium flag.
struct BannerAdZone: View {
    let provider: AdProvider

    var body: some View {
        if !provider.isPremium {
            provider.loadBanner()
        }
    }
}

struct NativeAdCell: View {
    let provider: AdProvider

    var body: some View {
        if !provider.isPremium {
            provider.loadNativeAd()
        }
    }
}
