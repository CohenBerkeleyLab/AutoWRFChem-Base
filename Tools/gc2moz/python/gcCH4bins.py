
import sys
__author__ = 'Josh'

north_lats = (30.0, 90.0)
north_trop_lats = (0.0, 30.0)
south_trop_lats = (-30.0, 0.0)
south_lats = (-90.0, 30.0)

def shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)


def shell_msg(msg):
    print(msg, file=sys.stderr)


def get_global_ch4(year):
    north, north_trop, south_trop, south = __ch4(year)
    return {'north': north, 'north_trop': north_trop, 'south_trop': south_trop, 'south': south}


def __ch4(year):
    # Pretty much directly copied from get_global_CH4.F in GeosCore
    # Preindustrial years
    if year <= 1750:
        south = 700.0
        south_trop = 700.0
        north_trop = 700.0
        north = 700.0

    # Modern-day years ...
    elif year == 1983:
        south = 1583.48
        south_trop = 1598.24
        north_trop = 1644.37
        north = 1706.48

    elif year == 1984:
        south = 1597.77
        south_trop = 1606.66
        north_trop = 1655.62
        north = 1723.63

    elif year == 1985:
        south = 1608.08
        south_trop = 1620.43
        north_trop = 1668.11
        north = 1736.78

    elif year == 1986:
        south = 1619.91
        south_trop = 1632.24
        north_trop = 1682.88
        north = 1752.71

    elif year == 1987:
        south = 1630.54
        south_trop = 1640.54
        north_trop = 1702.05
        north = 1763.03

    elif year == 1988:
        south = 1642.08
        south_trop = 1651.60
        north_trop = 1713.07
        north = 1775.66

    elif year == 1989:
        south = 1654.03
        south_trop = 1666.12
        north_trop = 1720.53
        north = 1781.83

    elif year == 1990:
        south = 1663.21
        south_trop = 1672.45
        north_trop = 1733.84
        north = 1791.92

    elif year == 1991:
        south = 1673.52
        south_trop = 1683.87
        north_trop = 1750.68
        north = 1800.90

    elif year == 1992:
        south = 1687.97
        south_trop = 1692.97
        north_trop = 1755.94
        north = 1807.16

    elif year == 1993:
        south = 1687.83
        south_trop = 1696.48
        north_trop = 1758.86
        north = 1810.99

    elif year == 1994:
        south = 1692.00
        south_trop = 1701.41
        north_trop = 1766.98
        north = 1817.12

    elif year == 1995:
        south = 1701.04
        south_trop = 1709.07
        north_trop = 1778.25
        north = 1822.04

    elif year == 1996:
        south = 1701.87
        south_trop = 1711.01
        north_trop = 1778.08
        north = 1825.23

    elif year == 1997:
        south = 1708.01
        south_trop = 1713.91
        north_trop = 1781.43
        north = 1825.15

    elif year == 1998:
        south = 1716.55
        south_trop = 1724.57
        north_trop = 1783.86
        north = 1839.72

    elif year == 1999:
        south = 1725.70
        south_trop = 1734.06
        north_trop = 1791.50
        north = 1842.59

    elif year == 2000:
        south = 1728.13
        south_trop = 1737.70
        north_trop = 1792.42
        north = 1840.83

    elif year == 2001:
        south = 1726.92
        south_trop = 1730.72
        north_trop = 1789.11
        north = 1841.85

    elif year == 2002:
        south = 1729.75
        south_trop = 1735.28
        north_trop = 1790.08
        north = 1842.36

    elif year == 2003:
        south = 1729.64
        south_trop = 1735.49
        north_trop = 1795.89
        north = 1853.97

    elif year == 2004:
        south = 1728.72
        south_trop = 1738.54
        north_trop = 1797.30
        north = 1849.58

    elif year == 2005:
        south = 1727.10
        south_trop = 1734.65
        north_trop = 1795.73
        north = 1849.79

    elif year == 2006:
        south = 1726.53
        south_trop = 1735.17
        north_trop = 1796.30
        north = 1848.20

    elif year >= 2007:
        south = 1732.52
        south_trop = 1741.68
        north_trop = 1801.38
        north = 1855.55

        if year > 2007:
            shell_msg('Using 2007 CH4 bins, 2007 is last year with reported data in GEOS-Chem v9-02')

    else:
        raise ValueError('CH4 not defined for {0}'.format(year))

    # Convert from ppb to straight VMR
    north *= 1e-9
    north_trop *= 1e-9
    south_trop *= 1e-9
    south *= 1e-9

    return north, north_trop, south_trop, south
