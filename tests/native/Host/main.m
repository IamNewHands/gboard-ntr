// Minimal UIKit host for the action-display XCTest bundle; no Gboard injection.
#import <UIKit/UIKit.h>
#import <execinfo.h>
#import <signal.h>
#import <unistd.h>

// Temporary CI diagnosis: the fixture host dies with SIGSEGV before XCTest can
// report anything. Print the faulting stack from a dedicated signal stack so a
// stack overflow is still observable. Remove with the other [DEBUG-native-ci]
// probes once the shared crash is fixed.
#define GXK_CRASH_STACK_BYTES (64 * 1024)
static char gCrashAltStack[GXK_CRASH_STACK_BYTES];

static void GXKCrashHandler(int sig) {
    void *frames[96];
    int count = backtrace(frames, 96);
    static const char header[] = "\n[DEBUG-native-ci] fatal signal, stack follows\n";
    ssize_t written = write(STDERR_FILENO, header, sizeof(header) - 1);
    (void)written;
    backtrace_symbols_fd(frames, count, STDERR_FILENO);
    _exit(128 + sig);
}

static void GXKInstallCrashHandler(void) {
    stack_t stack = {0};
    stack.ss_sp = gCrashAltStack;
    stack.ss_size = sizeof(gCrashAltStack);
    sigaltstack(&stack, NULL);
    const int signals[] = {SIGSEGV, SIGBUS, SIGABRT, SIGILL, SIGFPE};
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); i++) {
        struct sigaction action = {0};
        action.sa_handler = GXKCrashHandler;
        action.sa_flags = SA_ONSTACK | SA_RESETHAND;
        sigemptyset(&action.sa_mask);
        sigaction(signals[i], &action, NULL);
    }
}

@interface GXKNativeHostDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation GXKNativeHostDelegate
- (BOOL)application:(UIApplication *)application
    didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController *controller = [[UIViewController alloc] init];
    controller.view.backgroundColor = UIColor.clearColor;
    self.window.backgroundColor = UIColor.clearColor;
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    return YES;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        GXKInstallCrashHandler();
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(GXKNativeHostDelegate.class));
    }
}