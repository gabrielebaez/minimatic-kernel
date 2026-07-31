from minimatic import Kernel


k = Kernel()
result = k.eval_file('./examples/tour.md')


if __name__ == "__main__":
    print(result)
