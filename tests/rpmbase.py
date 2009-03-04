import os

from mocker import MockerTestCase

from smart.backends.rpm.base import RPMPackage, Package, getTS
from smart import sysconf


class getTSTest(MockerTestCase):

    def test_wb_rpm_root_path_must_be_absolute(self):
        """
        Somewhat of a weak test.  I haven't managed to make the code
        break when rpm root isn't absolute, so I decided to do a whitebox
        test and verify that at least the fix which is mentioned in
        #307386 is in place.
        """
        current_path = os.getcwd()
        test_path = self.makeDir()
        os.chdir(test_path)
        self.addCleanup(lambda: os.chdir(current_path))
        sysconf.set("rpm-root", "relative-rpm-root")
        ts = getTS()
        self.assertEquals(getTS.root, "%s/relative-rpm-root" % test_path)



class RPMPackageTest(MockerTestCase):

    def test_sorting_name_takes_precedence(self):
        pkg1 = RPMPackage("name1", "3.0-1@i386")
        pkg2 = RPMPackage("name2", "1.0-1@i386")
        pkg3 = RPMPackage("name3", "2.0-1@i386")
        lst = [pkg3, pkg1, pkg2]
        lst.sort()
        self.assertEquals(lst, [pkg1, pkg2, pkg3])

    def test_sorting_uses_name_when_different_package_types(self):
        pkg1 = RPMPackage("name1", "3.0-1@i386")
        pkg2 = Package("name2", "1.0-1@i386")
        pkg3 = Package("name3", "2.0-1@i386")
        lst = [pkg3, pkg1, pkg2]
        lst.sort()
        self.assertEquals(lst, [pkg1, pkg2, pkg3])

    def test_sorting_version_takes_precedence_over_arch(self):
        pkg1 = RPMPackage("name", "1.0-1@i386")
        pkg2 = RPMPackage("name", "2.0-1@i686")
        pkg3 = RPMPackage("name", "3.0-1@i386")
        lst = [pkg3, pkg1, pkg2]
        lst.sort()
        self.assertEquals(lst, [pkg1, pkg2, pkg3])

    def test_sorting_arch_used_when_same_version(self):
        pkg1 = RPMPackage("name", "1.0-1@i386")
        pkg2 = RPMPackage("name", "1.0-1@i586")
        pkg3 = RPMPackage("name", "1.0-1@i686")
        lst = [pkg3, pkg1, pkg2]
        lst.sort()
        self.assertEquals(lst, [pkg1, pkg2, pkg3])

    def test_sorting_color_takes_precedence_over_version(self):
        pkg1 = RPMPackage("name", "1.0-1@x86_64")
        pkg2 = RPMPackage("name", "2.0-1@i386")
        pkg3 = RPMPackage("name", "3.0-1@i386")
        lst = [pkg1, pkg2, pkg3]
        lst.sort()
        self.assertEquals(lst, [pkg2, pkg3, pkg1])
